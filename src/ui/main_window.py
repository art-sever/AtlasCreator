from __future__ import annotations

import shutil
import math
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QThreadPool, Qt, QUrl, Slot
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.app_state import AppState
from src.models import AtlasParams, BackgroundRemovalParams, ExtractMode, ExtractionParams, ResizeMode, VideoMeta
from src.services.atlas_service import AtlasService
from src.services.background_service import BackgroundService
from src.services.image_service import ImageService
from src.services.tooling_service import ToolingService
from src.services.video_service import VideoService
from src.ui.spritesheet_preview_dialog import SpriteSheetPreviewDialog
from src.ui.workers import TaskWorker


class MainWindow(QMainWindow):
    FRAME_SIZE_OPTIONS = (16, 32, 64, 128, 256, 512, 1024)
    PREVIEW_BACKGROUND_OPTIONS = (
        ("Black", "#000000", "#cccccc"),
        ("White", "#ffffff", "#111111"),
        ("Green", "#00ff00", "#111111"),
    )

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("AtlasCreator - Video to SpriteSheet")
        self.resize(1480, 900)

        project_root = Path(__file__).resolve().parents[2]
        self.state = AppState.create(project_root)
        self.state.prepare_temp_dirs(clean=True)

        self.tooling_service = ToolingService()
        self.video_service = VideoService()
        self.background_service = BackgroundService(self.tooling_service)
        self.image_service = ImageService()
        self.atlas_service = AtlasService()

        self.thread_pool = QThreadPool.globalInstance()
        self._active_workers: set[TaskWorker] = set()
        self._busy = False
        self._auto_remove_pending = False
        self._auto_build_pending = False
        self._is_playing = False
        self._syncing_timeline = False
        self._is_closing = False
        self._pending_build_context: tuple[AtlasParams, int] | None = None
        self._preview_atlas_params: AtlasParams | None = None
        self._preview_frame_count = 0
        self._spritesheet_preview_dialog: SpriteSheetPreviewDialog | None = None

        self._build_ui()
        self._setup_media_player()
        self._connect_signals()
        self._update_sampling_mode_ui()
        self._update_atlas_params_label()
        self._apply_preview_background()
        self._refresh_action_states()
        self._set_status("Готово. Загрузите видео")

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        top_layout = QHBoxLayout()
        root_layout.addLayout(top_layout, 1)

        left_group = self._build_left_panel()
        center_group = self._build_pipeline_panel()
        right_group = self._build_right_panel()

        top_layout.addWidget(left_group, 2)
        top_layout.addWidget(center_group, 2)
        top_layout.addWidget(right_group, 2)

        atlas_group = self._build_atlas_panel()
        root_layout.addWidget(atlas_group)

        status_row = QHBoxLayout()
        self.status_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.progress_bar, 1)
        root_layout.addLayout(status_row)

        activity_row = QHBoxLayout()
        self.activity_label = QLabel("Идет обработка...")
        self.activity_bar = QProgressBar()
        # Диапазон 0..0 включает «бесконечный» режим и явно показывает, что задача выполняется.
        self.activity_bar.setRange(0, 0)
        self.activity_bar.setTextVisible(False)
        self.activity_label.setVisible(False)
        self.activity_bar.setVisible(False)
        activity_row.addWidget(self.activity_label)
        activity_row.addWidget(self.activity_bar, 1)
        root_layout.addLayout(activity_row)

    def _build_left_panel(self) -> QGroupBox:
        group = QGroupBox("Видео")
        layout = QVBoxLayout(group)

        self.load_video_button = QPushButton("Load Video")
        layout.addWidget(self.load_video_button)

        self.video_info_label = QLabel("Видео не загружено")
        self.video_info_label.setWordWrap(True)
        layout.addWidget(self.video_info_label)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(420, 240)
        self.video_widget.setStyleSheet("border: 1px solid #777; background: #111;")
        layout.addWidget(self.video_widget, 1)

        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 0)
        layout.addWidget(self.timeline_slider)

        controls_row = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        self.prev_frame_button = QPushButton("Prev Frame")
        self.next_frame_button = QPushButton("Next Frame")
        controls_row.addWidget(self.play_button)
        controls_row.addWidget(self.pause_button)
        controls_row.addWidget(self.prev_frame_button)
        controls_row.addWidget(self.next_frame_button)
        layout.addLayout(controls_row)

        return group

    def _setup_media_player(self) -> None:
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        # Превью в приложении не требует звука, отключаем его по умолчанию.
        self.audio_output.setVolume(0.0)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setLoops(QMediaPlayer.Loops.Infinite)

    def _build_pipeline_panel(self) -> QGroupBox:
        group = QGroupBox("Пайплайн")
        layout = QVBoxLayout(group)

        self.sampling_mode_combo = QComboBox()
        self.sampling_mode_combo.addItem("Target FPS", ExtractMode.TARGET_FPS)
        self.sampling_mode_combo.addItem("Exact Frame Count", ExtractMode.EXACT_COUNT)
        # По умолчанию используем точное количество кадров для предсказуемой выборки.
        self.sampling_mode_combo.setCurrentIndex(1)
        layout.addWidget(QLabel("Режим выборки кадров"))
        layout.addWidget(self.sampling_mode_combo)

        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(0.1, 240.0)
        self.fps_spin.setDecimals(2)
        self.fps_spin.setValue(8.0)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 2000)
        self.count_spin.setValue(8)

        self.fps_label = QLabel("FPS")
        self.count_label = QLabel("Count")
        layout.addWidget(self.fps_label)
        layout.addWidget(self.fps_spin)
        layout.addWidget(self.count_label)
        layout.addWidget(self.count_spin)

        self.extract_button = QPushButton("Extract Frames")
        self.remove_bg_button = QPushButton("Remove Background")
        self.auto_remove_checkbox = QCheckBox("Auto remove background after extraction")
        self.fg_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.fg_threshold_slider.setRange(0, 255)
        self.fg_threshold_slider.setValue(240)
        self.fg_threshold_value_label = QLabel("240")

        self.bg_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.bg_threshold_slider.setRange(0, 255)
        self.bg_threshold_slider.setValue(10)
        self.bg_threshold_value_label = QLabel("10")

        self.erode_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.erode_size_slider.setRange(0, 255)
        self.erode_size_slider.setValue(10)
        self.erode_size_value_label = QLabel("10")

        layout.addWidget(self.extract_button)
        layout.addWidget(self.remove_bg_button)
        layout.addWidget(self.auto_remove_checkbox)

        fg_row = QHBoxLayout()
        fg_row.addWidget(QLabel("FG Threshold"))
        fg_row.addWidget(self.fg_threshold_slider, 1)
        fg_row.addWidget(self.fg_threshold_value_label)
        layout.addLayout(fg_row)

        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel("BG Threshold"))
        bg_row.addWidget(self.bg_threshold_slider, 1)
        bg_row.addWidget(self.bg_threshold_value_label)
        layout.addLayout(bg_row)

        erode_row = QHBoxLayout()
        erode_row.addWidget(QLabel("Erode Size"))
        erode_row.addWidget(self.erode_size_slider, 1)
        erode_row.addWidget(self.erode_size_value_label)
        layout.addLayout(erode_row)
        layout.addStretch(1)

        return group

    def _build_right_panel(self) -> QGroupBox:
        group = QGroupBox("SpriteSheet")
        layout = QVBoxLayout(group)

        self.atlas_preview_label = QLabel("SpriteSheet Preview")
        self.atlas_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.atlas_preview_label.setMinimumSize(420, 240)
        self.atlas_preview_label.setStyleSheet("border: 1px solid #777;")
        layout.addWidget(self.atlas_preview_label, 1)

        background_row = QHBoxLayout()
        background_row.addWidget(QLabel("Preview Background"))
        self.preview_background_combo = QComboBox()
        for label, bg_color, text_color in self.PREVIEW_BACKGROUND_OPTIONS:
            self.preview_background_combo.addItem(label, (bg_color, text_color))
        background_row.addWidget(self.preview_background_combo, 1)
        layout.addLayout(background_row)

        self.preview_video_button = QPushButton("Video Preview")
        layout.addWidget(self.preview_video_button)

        self.atlas_params_label = QLabel("Параметры atlas не заданы")
        self.atlas_params_label.setWordWrap(True)
        layout.addWidget(self.atlas_params_label)

        return group

    def _build_atlas_panel(self) -> QGroupBox:
        group = QGroupBox("Настройки atlas")
        layout = QGridLayout(group)

        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 1024)
        self.columns_spin.setValue(4)

        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 1024)
        self.rows_spin.setValue(2)

        self.frame_width_combo = QComboBox()
        self.frame_height_combo = QComboBox()
        for size in self.FRAME_SIZE_OPTIONS:
            self.frame_width_combo.addItem(str(size), size)
            self.frame_height_combo.addItem(str(size), size)
        self.frame_width_combo.setCurrentText("512")
        self.frame_height_combo.setCurrentText("512")

        self.resize_mode_combo = QComboBox()
        self.resize_mode_combo.addItem("Keep Aspect + Fit", ResizeMode.FIT)
        self.resize_mode_combo.addItem("Crop Center", ResizeMode.CROP_CENTER)
        self.resize_mode_combo.addItem("Stretch", ResizeMode.STRETCH)

        self.build_button = QPushButton("Build SpriteSheet")
        self.export_button = QPushButton("Export PNG")

        layout.addWidget(QLabel("Columns"), 0, 0)
        layout.addWidget(self.columns_spin, 0, 1)
        layout.addWidget(QLabel("Rows"), 0, 2)
        layout.addWidget(self.rows_spin, 0, 3)

        layout.addWidget(QLabel("Frame Width"), 1, 0)
        layout.addWidget(self.frame_width_combo, 1, 1)
        layout.addWidget(QLabel("Frame Height"), 1, 2)
        layout.addWidget(self.frame_height_combo, 1, 3)

        layout.addWidget(QLabel("Resize Mode"), 2, 0)
        layout.addWidget(self.resize_mode_combo, 2, 1, 1, 3)

        layout.addWidget(self.build_button, 3, 2)
        layout.addWidget(self.export_button, 3, 3)

        return group

    def _connect_signals(self) -> None:
        self.load_video_button.clicked.connect(self._load_video)
        self.timeline_slider.valueChanged.connect(self._on_timeline_changed)
        self.media_player.positionChanged.connect(self._on_player_position_changed)
        self.media_player.durationChanged.connect(self._on_player_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)

        self.play_button.clicked.connect(self._play_video)
        self.pause_button.clicked.connect(self._pause_video)
        self.prev_frame_button.clicked.connect(self._prev_frame)
        self.next_frame_button.clicked.connect(self._next_frame)

        self.sampling_mode_combo.currentIndexChanged.connect(self._update_sampling_mode_ui)

        self.extract_button.clicked.connect(self._extract_frames)
        self.remove_bg_button.clicked.connect(self._remove_background)
        self.build_button.clicked.connect(self._build_spritesheet)
        self.preview_video_button.clicked.connect(self._open_spritesheet_preview)
        self.export_button.clicked.connect(self._export_png)
        self.preview_background_combo.currentIndexChanged.connect(self._on_preview_background_changed)

        self.columns_spin.valueChanged.connect(self._update_atlas_params_label)
        self.rows_spin.valueChanged.connect(self._update_atlas_params_label)
        self.frame_width_combo.currentIndexChanged.connect(self._update_atlas_params_label)
        self.frame_height_combo.currentIndexChanged.connect(self._update_atlas_params_label)
        self.resize_mode_combo.currentIndexChanged.connect(self._update_atlas_params_label)
        self.fg_threshold_slider.valueChanged.connect(self._on_fg_threshold_changed)
        self.bg_threshold_slider.valueChanged.connect(self._on_bg_threshold_changed)
        self.erode_size_slider.valueChanged.connect(self._on_erode_size_changed)

    @Slot(int)
    def _on_fg_threshold_changed(self, value: int) -> None:
        self.fg_threshold_value_label.setText(str(value))

    @Slot(int)
    def _on_bg_threshold_changed(self, value: int) -> None:
        self.bg_threshold_value_label.setText(str(value))

    @Slot(int)
    def _on_erode_size_changed(self, value: int) -> None:
        self.erode_size_value_label.setText(str(value))

    @Slot()
    def _load_video(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите видео",
            "",
            "Video Files (*.mp4 *.mov *.m4v *.avi *.mkv)",
        )
        if not file_path:
            return

        try:
            self.tooling_service.ensure_ffmpeg_tools()
            video_path = Path(file_path)
            metadata = self.video_service.get_metadata(video_path)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Не удалось загрузить видео: {exc}")
            return

        self._pause_video()
        self.state.video_path = video_path
        self.state.video_meta = metadata
        self.state.reset_pipeline_outputs()
        self.state.prepare_temp_dirs(clean=True)

        self._update_video_info(metadata)
        max_position = max(0, int(metadata.duration_sec * 1000))
        self.timeline_slider.setRange(0, max_position)
        self.timeline_slider.setValue(0)
        self.media_player.setSource(QUrl.fromLocalFile(str(video_path.resolve())))
        self.media_player.setPosition(0)

        self.atlas_preview_label.setPixmap(QPixmap())
        self._reset_spritesheet_preview_state(close_dialog=True)
        self._set_status(f"Видео загружено: {video_path.name}")
        self._refresh_action_states()

    def _update_video_info(self, metadata: VideoMeta) -> None:
        info_lines = [
            f"Path: {metadata.path}",
            f"Duration: {metadata.duration_sec:.2f} sec",
            f"Resolution: {metadata.width}x{metadata.height}",
            f"FPS: {metadata.fps:.3f}",
            f"Frames (estimate): {metadata.frame_count_estimate}",
        ]
        self.video_info_label.setText("\n".join(info_lines))

    @Slot(int)
    def _on_timeline_changed(self, value: int) -> None:
        if self.state.video_path is None or self._syncing_timeline:
            return
        if self.media_player.source().isEmpty():
            return
        self.media_player.setPosition(value)

    @Slot(int)
    def _on_player_position_changed(self, position_ms: int) -> None:
        clamped_position = max(self.timeline_slider.minimum(), min(self.timeline_slider.maximum(), position_ms))
        self._syncing_timeline = True
        blocker = QSignalBlocker(self.timeline_slider)
        self.timeline_slider.setValue(clamped_position)
        del blocker
        self._syncing_timeline = False

    @Slot(int)
    def _on_player_duration_changed(self, duration_ms: int) -> None:
        if self.state.video_meta is None:
            return
        fallback_duration_ms = int(self.state.video_meta.duration_sec * 1000)
        max_position = max(0, duration_ms, fallback_duration_ms)
        blocker = QSignalBlocker(self.timeline_slider)
        self.timeline_slider.setRange(0, max_position)
        del blocker

    @Slot(QMediaPlayer.PlaybackState)
    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self._is_playing = state == QMediaPlayer.PlaybackState.PlayingState

    @Slot(int)
    def _on_preview_background_changed(self, _index: int) -> None:
        self._apply_preview_background()

    def _current_preview_background(self) -> tuple[str, str]:
        data = self.preview_background_combo.currentData()
        if (
            isinstance(data, tuple)
            and len(data) == 2
            and isinstance(data[0], str)
            and isinstance(data[1], str)
        ):
            return data[0], data[1]
        return "#000000", "#cccccc"

    def _apply_preview_background(self) -> None:
        # Оба предпросмотра используют единый цвет фона, чтобы пользователь видел одинаковый результат.
        bg_color, text_color = self._current_preview_background()
        self.atlas_preview_label.setStyleSheet(
            f"border: 1px solid #777; background: {bg_color}; color: {text_color};"
        )
        if self._spritesheet_preview_dialog is not None:
            self._spritesheet_preview_dialog.set_preview_background(bg_color, text_color)

    def _set_preview_image(self, target: QLabel, image_path: Path) -> None:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            target.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        target.setPixmap(scaled)

    def _play_video(self) -> None:
        if self.state.video_meta is None or self._busy:
            return
        if self.timeline_slider.value() >= self.timeline_slider.maximum():
            self.media_player.setPosition(self.timeline_slider.minimum())
        self.media_player.play()

    def _pause_video(self) -> None:
        self.media_player.pause()

    def _frame_step_ms(self) -> int:
        if self.state.video_meta is None or self.state.video_meta.fps <= 0:
            return 40
        return max(1, int(round(1000.0 / self.state.video_meta.fps)))

    def _prev_frame(self) -> None:
        position = self.media_player.position() - self._frame_step_ms()
        self.media_player.setPosition(max(self.timeline_slider.minimum(), position))

    def _next_frame(self) -> None:
        position = self.media_player.position() + self._frame_step_ms()
        self.media_player.setPosition(min(self.timeline_slider.maximum(), position))

    def _update_sampling_mode_ui(self) -> None:
        mode = self._current_extract_mode()
        is_fps_mode = mode == ExtractMode.TARGET_FPS
        self.fps_label.setVisible(is_fps_mode)
        self.fps_spin.setVisible(is_fps_mode)
        self.count_label.setVisible(not is_fps_mode)
        self.count_spin.setVisible(not is_fps_mode)

    def _current_extract_mode(self) -> ExtractMode:
        data = self.sampling_mode_combo.currentData()
        if isinstance(data, ExtractMode):
            return data
        if isinstance(data, str):
            try:
                return ExtractMode(data)
            except ValueError:
                return ExtractMode.TARGET_FPS
        return ExtractMode.TARGET_FPS

    def _collect_extraction_params(self) -> ExtractionParams:
        mode = self._current_extract_mode()
        if mode == ExtractMode.TARGET_FPS:
            params = ExtractionParams(mode=mode, target_fps=float(self.fps_spin.value()))
        else:
            params = ExtractionParams(mode=mode, exact_count=int(self.count_spin.value()))
        params.validate()
        return params

    def _collect_atlas_params(self) -> AtlasParams:
        params = AtlasParams(
            columns=int(self.columns_spin.value()),
            rows=int(self.rows_spin.value()),
            frame_width=self._current_frame_size(self.frame_width_combo),
            frame_height=self._current_frame_size(self.frame_height_combo),
            resize_mode=self._current_resize_mode(),
        )
        params.validate()
        return params

    def _collect_background_removal_params(self) -> BackgroundRemovalParams:
        params = BackgroundRemovalParams(
            fg_threshold=int(self.fg_threshold_slider.value()),
            bg_threshold=int(self.bg_threshold_slider.value()),
            erode_size=int(self.erode_size_slider.value()),
        )
        params.validate()
        return params

    def _current_frame_size(self, combo: QComboBox) -> int:
        data = combo.currentData()
        if isinstance(data, int):
            return data
        if isinstance(data, str) and data.isdigit():
            return int(data)
        return 512

    def _current_resize_mode(self) -> ResizeMode:
        data = self.resize_mode_combo.currentData()
        if isinstance(data, ResizeMode):
            return data
        if isinstance(data, str):
            try:
                return ResizeMode(data)
            except ValueError:
                return ResizeMode.FIT
        return ResizeMode.FIT

    def _extract_frames(self) -> None:
        if self._busy:
            return
        if self.state.video_path is None:
            self._show_error("Сначала выберите видео")
            return

        try:
            self.tooling_service.ensure_ffmpeg_tools()
            params = self._collect_extraction_params()
        except Exception as exc:  # noqa: BLE001
            self._show_error(str(exc))
            return

        self.state.prepare_temp_dirs(clean=True)
        self.state.reset_pipeline_outputs()
        self._auto_remove_pending = False
        self._auto_build_pending = False
        self._refresh_action_states()

        worker = TaskWorker(self.video_service.extract_frames, self.state.video_path, params, self.state.frames_dir)
        worker.signals.progress.connect(self._on_worker_progress, Qt.ConnectionType.QueuedConnection)
        worker.signals.result.connect(self._on_extract_completed, Qt.ConnectionType.QueuedConnection)
        worker.signals.error.connect(
            lambda msg: self._on_worker_error("Не удалось извлечь кадры", msg),
            Qt.ConnectionType.QueuedConnection,
        )
        self._start_worker(worker, "Извлечение кадров")

    def _on_extract_completed(self, frames: list[Path]) -> None:
        self.state.extracted_frames = sorted(frames, key=VideoService.parse_frame_index_from_filename)
        self.state.cut_frames = []
        self.state.atlas_path = None
        self.atlas_preview_label.setPixmap(QPixmap())
        self._reset_spritesheet_preview_state(close_dialog=True)
        self._set_status(f"Извлечено кадров: {len(self.state.extracted_frames)}")

        self._auto_build_pending = bool(self.state.extracted_frames)

        if self.auto_remove_checkbox.isChecked() and self.state.extracted_frames:
            self._auto_remove_pending = True

        self._refresh_action_states()

    def _remove_background(self) -> None:
        if self._busy:
            return
        if not self.state.extracted_frames:
            self._show_error("Сначала извлеките кадры")
            return
        try:
            self.tooling_service.ensure_rembg_remove()
            background_params = self._collect_background_removal_params()
        except Exception as exc:  # noqa: BLE001
            self._show_error(str(exc))
            return

        worker = TaskWorker(
            self.background_service.remove_background_batch,
            self.state.extracted_frames,
            self.state.cut_dir,
            background_params,
        )
        worker.signals.progress.connect(self._on_worker_progress, Qt.ConnectionType.QueuedConnection)
        worker.signals.result.connect(self._on_remove_background_completed, Qt.ConnectionType.QueuedConnection)
        worker.signals.error.connect(
            lambda msg: self._on_worker_error("Не удалось удалить фон", msg),
            Qt.ConnectionType.QueuedConnection,
        )
        self._start_worker(worker, "Удаление фона")

    def _on_remove_background_completed(self, frames: list[Path]) -> None:
        self.state.cut_frames = sorted(frames, key=VideoService.parse_frame_index_from_filename)
        self._set_status(f"Фон удален для кадров: {len(self.state.cut_frames)}")
        self._refresh_action_states()

    def _build_spritesheet(self) -> None:
        if self._busy:
            return

        source_frames = self.state.cut_frames or self.state.extracted_frames
        if not source_frames:
            self._show_error("Нет кадров для сборки spritesheet")
            return

        try:
            atlas_params = self._collect_atlas_params()
        except Exception as exc:  # noqa: BLE001
            self._show_error(str(exc))
            return

        frame_count = len(source_frames)
        if frame_count > atlas_params.capacity:
            self._handle_capacity_overflow(frame_count, atlas_params)
            return

        self.state.atlas_path = None
        self._pending_build_context = (atlas_params, frame_count)
        self._reset_spritesheet_preview_state(close_dialog=True)
        self._refresh_action_states()

        output_path = self.state.output_dir / "spritesheet.png"
        worker = TaskWorker(self._build_spritesheet_task, source_frames, atlas_params, output_path)
        worker.signals.progress.connect(self._on_worker_progress, Qt.ConnectionType.QueuedConnection)
        worker.signals.result.connect(self._on_build_completed, Qt.ConnectionType.QueuedConnection)
        worker.signals.error.connect(
            lambda msg: self._on_worker_error("Не удалось собрать spritesheet", msg),
            Qt.ConnectionType.QueuedConnection,
        )
        self._start_worker(worker, "Сборка spritesheet")

    def _build_spritesheet_task(
        self,
        source_frames: list[Path],
        atlas_params: AtlasParams,
        output_path: Path,
        progress_cb,
    ) -> Path:
        # Делим прогресс на 2 этапа: подготовка кадров и сборка итогового atlas.
        prepared_frames = self.image_service.prepare_frames(
            source_frames,
            width=atlas_params.frame_width,
            height=atlas_params.frame_height,
            mode=atlas_params.resize_mode,
            progress_cb=lambda value, _msg: progress_cb(int(value * 0.6), "Подготовка кадров"),
        )

        return self.atlas_service.build_spritesheet(
            prepared_frames,
            atlas_params,
            output_path,
            progress_cb=lambda value, _msg: progress_cb(60 + int(value * 0.4), "Сборка spritesheet"),
        )

    def _on_build_completed(self, output_path: Path) -> None:
        self.state.atlas_path = output_path
        if output_path.exists():
            self._set_preview_image(self.atlas_preview_label, output_path)
        if self._pending_build_context is not None:
            self._preview_atlas_params, self._preview_frame_count = self._pending_build_context
        self._set_status(f"Spritesheet собран: {output_path.name}")
        self._refresh_action_states()

    def _handle_capacity_overflow(self, frame_count: int, atlas_params: AtlasParams) -> None:
        capacity = atlas_params.capacity
        needed_rows = math.ceil(frame_count / atlas_params.columns)
        message = (
            "Число кадров больше, чем вместимость atlas.\n\n"
            f"Кадров: {frame_count}\n"
            f"Вместимость: {capacity} ({atlas_params.columns} x {atlas_params.rows})\n"
            f"Минимально нужно Rows: {needed_rows} при Columns={atlas_params.columns}\n\n"
            "Нажмите Yes, чтобы автоматически выставить Rows."
        )
        result = QMessageBox.question(
            self,
            "Недостаточная вместимость atlas",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if result == QMessageBox.StandardButton.Yes:
            # Автоматически увеличиваем количество строк до минимально достаточного значения.
            self.rows_spin.setValue(needed_rows)
            self._update_atlas_params_label()
            self._set_status(f"Rows обновлен до {needed_rows}. Повторите Build SpriteSheet.")

    def _export_png(self) -> None:
        if self.state.atlas_path is None or not self.state.atlas_path.exists():
            self._show_error("Сначала соберите spritesheet")
            return

        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт PNG",
            "spritesheet.png",
            "PNG Files (*.png)",
        )
        if not destination:
            return

        try:
            shutil.copy2(self.state.atlas_path, Path(destination))
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Не удалось экспортировать PNG: {exc}")
            return

        self._set_status(f"PNG экспортирован: {destination}")

    def _update_atlas_params_label(self) -> None:
        try:
            params = self._collect_atlas_params()
            self.atlas_params_label.setText(
                " | ".join(
                    [
                        f"Columns: {params.columns}",
                        f"Rows: {params.rows}",
                        f"Frame: {params.frame_width}x{params.frame_height}",
                        f"Resize: {params.resize_mode.value}",
                        f"Sheet: {params.sheet_width}x{params.sheet_height}",
                    ]
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.atlas_params_label.setText(f"Некорректные параметры atlas: {exc}")

    def _refresh_action_states(self) -> None:
        has_video = self.state.video_path is not None
        has_frames = bool(self.state.extracted_frames)
        has_sheet = self.state.atlas_path is not None and self.state.atlas_path.exists()
        has_preview_data = self._preview_atlas_params is not None and self._preview_frame_count > 0

        enabled = not self._busy
        self.load_video_button.setEnabled(enabled)
        self.extract_button.setEnabled(enabled and has_video)
        self.remove_bg_button.setEnabled(enabled and has_frames)
        self.build_button.setEnabled(enabled and has_frames)
        self.preview_video_button.setEnabled(enabled and has_sheet and has_preview_data)
        self.export_button.setEnabled(enabled and has_sheet)

        self.timeline_slider.setEnabled(enabled and has_video)
        self.play_button.setEnabled(enabled and has_video)
        self.pause_button.setEnabled(enabled and has_video)
        self.prev_frame_button.setEnabled(enabled and has_video)
        self.next_frame_button.setEnabled(enabled and has_video)

    def _set_busy(self, busy: bool, operation: str = "") -> None:
        self._busy = busy
        if busy:
            self.progress_bar.setValue(0)
            self.activity_label.setVisible(True)
            self.activity_bar.setVisible(True)
            if operation:
                self._set_status(f"Выполняется: {operation}")
        else:
            self.activity_label.setVisible(False)
            self.activity_bar.setVisible(False)
        self._refresh_action_states()

    def _on_worker_progress(self, value: int, message: str) -> None:
        if self._is_closing:
            return
        self.progress_bar.setValue(value)
        if message:
            self._set_status(message)

    def _on_worker_error(self, title: str, details: str) -> None:
        if self._is_closing:
            return
        self._set_status(f"{title}: {details}")
        self._show_error(f"{title}: {details}")

    def _start_worker(self, worker: TaskWorker, operation: str) -> None:
        # Храним ссылку на воркер, чтобы Python-объект не уничтожился до завершения задачи.
        self._active_workers.add(worker)
        worker.signals.finished.connect(
            lambda w=worker: self._on_worker_finished(w),
            Qt.ConnectionType.QueuedConnection,
        )
        self._set_busy(True, operation)
        self.thread_pool.start(worker)

    def _on_worker_finished(self, worker: TaskWorker) -> None:
        self._active_workers.discard(worker)
        self._pending_build_context = None
        if self._is_closing:
            return
        self._set_busy(False)
        # После извлечения автоматически запускаем следующий шаг пайплайна:
        # сначала удаление фона (если включено), затем сборку spritesheet.
        if self._auto_remove_pending:
            self._auto_remove_pending = False
            self._remove_background()
            return
        if self._auto_build_pending:
            self._auto_build_pending = False
            self._build_spritesheet()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._is_closing = True
        self._reset_spritesheet_preview_state(close_dialog=True)
        self._pause_video()
        self.media_player.stop()
        self._auto_remove_pending = False
        self._auto_build_pending = False
        self.thread_pool.waitForDone(5000)
        self._active_workers.clear()
        super().closeEvent(event)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Ошибка", message)

    def _reset_spritesheet_preview_state(self, close_dialog: bool) -> None:
        self._preview_atlas_params = None
        self._preview_frame_count = 0
        if close_dialog and self._spritesheet_preview_dialog is not None:
            self._spritesheet_preview_dialog.close()
            self._spritesheet_preview_dialog = None

    @Slot()
    def _open_spritesheet_preview(self) -> None:
        if self.state.atlas_path is None or not self.state.atlas_path.exists():
            self._show_error("Сначала соберите spritesheet")
            return
        if self._preview_atlas_params is None or self._preview_frame_count <= 0:
            self._show_error("Нет данных для предпросмотра spritesheet")
            return

        if self._spritesheet_preview_dialog is not None:
            self._spritesheet_preview_dialog.close()
            self._spritesheet_preview_dialog = None

        preview_bg_color, preview_text_color = self._current_preview_background()
        dialog = SpriteSheetPreviewDialog(
            atlas_path=self.state.atlas_path,
            atlas_params=self._preview_atlas_params,
            frame_count=self._preview_frame_count,
            default_fps=self._default_spritesheet_preview_fps(),
            preview_background_color=preview_bg_color,
            preview_text_color=preview_text_color,
            parent=self,
        )
        dialog.finished.connect(self._on_spritesheet_preview_closed)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._spritesheet_preview_dialog = dialog

    @Slot(int)
    def _on_spritesheet_preview_closed(self, _result: int) -> None:
        self._spritesheet_preview_dialog = None

    def _default_spritesheet_preview_fps(self) -> float:
        mode = self._current_extract_mode()
        if mode == ExtractMode.TARGET_FPS:
            return float(self.fps_spin.value())
        if self.state.video_meta is not None and self.state.video_meta.fps > 0:
            return min(60.0, float(self.state.video_meta.fps))
        return 8.0
