from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from src.models import AtlasParams


class SpriteSheetPreviewDialog(QDialog):
    def __init__(
        self,
        atlas_path: Path,
        atlas_params: AtlasParams,
        frame_count: int,
        default_fps: float,
        preview_background_color: str,
        preview_text_color: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("SpriteSheet Video Preview")
        self.resize(760, 560)

        self._atlas_params = atlas_params
        self._frame_count = max(1, min(frame_count, atlas_params.capacity))
        self._frame_index = 0
        self._preview_background_color = preview_background_color
        self._preview_text_color = preview_text_color
        self._sheet_pixmap = QPixmap(str(atlas_path))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame_auto)

        self._build_ui(default_fps)
        self._update_timer_interval()
        self._render_current_frame()

    def _build_ui(self, default_fps: float) -> None:
        root_layout = QVBoxLayout(self)

        self.preview_label = QLabel("Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 360)
        self._apply_preview_background_style()
        root_layout.addWidget(self.preview_label, 1)

        self.frame_info_label = QLabel("")
        root_layout.addWidget(self.frame_info_label)

        controls_layout = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        self.prev_frame_button = QPushButton("Prev Frame")
        self.next_frame_button = QPushButton("Next Frame")
        controls_layout.addWidget(self.play_button)
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.prev_frame_button)
        controls_layout.addWidget(self.next_frame_button)

        fps_label = QLabel("FPS")
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 120.0)
        self.fps_spin.setDecimals(2)
        self.fps_spin.setValue(max(1.0, min(default_fps, 120.0)))
        controls_layout.addWidget(fps_label)
        controls_layout.addWidget(self.fps_spin)

        root_layout.addLayout(controls_layout)

        self.play_button.clicked.connect(self._play)
        self.pause_button.clicked.connect(self._pause)
        self.prev_frame_button.clicked.connect(self._prev_frame)
        self.next_frame_button.clicked.connect(self._next_frame)
        self.fps_spin.valueChanged.connect(self._update_timer_interval)

    def set_preview_background(self, background_color: str, text_color: str) -> None:
        self._preview_background_color = background_color
        self._preview_text_color = text_color
        self._apply_preview_background_style()

    def _apply_preview_background_style(self) -> None:
        # Фон для анимации синхронизируется с фоном в основном окне предпросмотра spritesheet.
        self.preview_label.setStyleSheet(
            f"border: 1px solid #777; background: {self._preview_background_color}; color: {self._preview_text_color};"
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._render_current_frame()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().closeEvent(event)

    def _play(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def _pause(self) -> None:
        self._timer.stop()

    def _update_timer_interval(self) -> None:
        fps = float(self.fps_spin.value())
        interval_ms = max(1, int(round(1000.0 / fps)))
        self._timer.setInterval(interval_ms)

    def _prev_frame(self) -> None:
        self._frame_index = (self._frame_index - 1) % self._frame_count
        self._render_current_frame()

    def _next_frame(self) -> None:
        self._frame_index = (self._frame_index + 1) % self._frame_count
        self._render_current_frame()

    def _next_frame_auto(self) -> None:
        self._next_frame()

    def _render_current_frame(self) -> None:
        if self._sheet_pixmap.isNull():
            self.preview_label.setText("Не удалось загрузить spritesheet")
            return

        frame_width = self._atlas_params.frame_width
        frame_height = self._atlas_params.frame_height
        columns = self._atlas_params.columns

        row = self._frame_index // columns
        col = self._frame_index % columns
        x = col * frame_width
        y = row * frame_height

        frame_pixmap = self._sheet_pixmap.copy(x, y, frame_width, frame_height)
        if frame_pixmap.isNull():
            self.preview_label.setText("Не удалось отрисовать кадр")
            return

        scaled = frame_pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.frame_info_label.setText(f"Кадр: {self._frame_index + 1}/{self._frame_count}")
