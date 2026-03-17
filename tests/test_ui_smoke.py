import os
from pathlib import Path

import pytest
from PIL import Image

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.models import AtlasParams, MediaKind, ResizeMode  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
from src.ui.workers import TaskWorker  # noqa: E402


def test_main_window_smoke() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert "AtlasCreator" in window.windowTitle()
    window.close()


def test_exact_count_mode_switches_input_field() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    # Переключаемся в режим точного количества кадров и проверяем, что активно поле Count.
    exact_index = -1
    for idx in range(window.sampling_mode_combo.count()):
        data = window.sampling_mode_combo.itemData(idx)
        if str(data) == "ExtractMode.EXACT_COUNT" or data == "exact_count":
            exact_index = idx
            break
    assert exact_index >= 0
    window.sampling_mode_combo.setCurrentIndex(exact_index)

    assert not window.count_spin.isHidden()
    assert window.fps_spin.isHidden()
    window.close()


def test_exact_count_mode_is_default() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.sampling_mode_combo.currentText() == "Exact Frame Count"
    assert not window.count_spin.isHidden()
    assert window.fps_spin.isHidden()
    window.close()


def test_frame_size_dropdowns_use_fixed_values() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    expected_sizes = [16, 32, 64, 128, 256, 512, 1024]
    actual_width_sizes = [window.frame_width_combo.itemData(idx) for idx in range(window.frame_width_combo.count())]
    actual_height_sizes = [window.frame_height_combo.itemData(idx) for idx in range(window.frame_height_combo.count())]

    assert actual_width_sizes == expected_sizes
    assert actual_height_sizes == expected_sizes
    assert window.frame_width_combo.currentData() == 512
    assert window.frame_height_combo.currentData() == 512
    window.close()


def test_extract_task_keeps_original_frame_size(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    out_dir = tmp_path / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    window.frame_width_combo.setCurrentText("64")
    window.frame_height_combo.setCurrentText("32")

    def _fake_extract(_video_path: Path, _params, target_dir: Path, progress_cb=None) -> list[Path]:
        created: list[Path] = []
        for index in range(2):
            frame_path = target_dir / f"frame_{index + 1:06d}.png"
            Image.new("RGBA", (120, 90), (255, 0, 0, 255)).save(frame_path)
            created.append(frame_path)
        if progress_cb is not None:
            progress_cb(100, "ok")
        return created

    window.video_service.extract_frames = _fake_extract  # type: ignore[method-assign]

    extracted = window._extract_frames_task(
        video_path=tmp_path / "input.mp4",
        extraction_params=window._collect_extraction_params(),
        frames_dir=out_dir,
        progress_cb=lambda _value, _message: None,
    )

    assert len(extracted) == 2
    for frame_path in extracted:
        with Image.open(frame_path) as frame_image:
            assert frame_image.size == (120, 90)
            assert frame_image.mode == "RGBA"

    window.close()


def test_spritesheet_video_preview_button_initially_disabled() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.preview_video_button.text() == "Video Preview"
    assert not window.preview_video_button.isEnabled()
    window.close()


def test_load_image_file_prepares_single_png_frame(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    image_path = tmp_path / "portrait.jpg"
    Image.new("RGB", (96, 64), (120, 80, 40)).save(image_path, format="JPEG")

    window._load_image_file(image_path)

    assert window.state.media_kind == MediaKind.IMAGE
    assert window.state.media_path == image_path
    assert window.state.video_path is None
    assert len(window.state.extracted_frames) == 1
    prepared_frame = window.state.extracted_frames[0]
    assert prepared_frame.exists()
    assert prepared_frame.suffix == ".png"
    assert window.remove_bg_button.isEnabled()
    assert window.crop_to_content_checkbox.isEnabled()
    assert not window.extract_button.isEnabled()
    assert "Type: image" in window.video_info_label.text()

    with Image.open(prepared_frame) as image:
        assert image.format == "PNG"
        assert image.mode == "RGBA"
        assert image.size == (96, 64)

    window.close()


def test_image_export_is_enabled_after_background_removal_without_spritesheet(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    window.state.media_kind = MediaKind.IMAGE
    window.state.media_path = tmp_path / "portrait.png"
    cut_frame = tmp_path / "cut" / "frame_000001.png"
    cut_frame.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (48, 48), (0, 0, 0, 0)).save(cut_frame)

    window._on_remove_background_completed([cut_frame])

    assert window.export_button.isEnabled()
    assert window._resolve_export_source() == cut_frame
    assert window._default_export_filename() == "portrait_transparent.png"
    window.close()


def test_preview_background_selector_has_expected_options() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    options = [window.preview_background_combo.itemText(idx) for idx in range(window.preview_background_combo.count())]
    assert options == ["Black", "White", "Green"]
    window.close()


def test_background_removal_controls_have_defaults() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.fg_threshold_slider.value() == 240
    assert window.bg_threshold_slider.value() == 10
    assert window.erode_size_slider.value() == 10
    assert window.crop_to_content_checkbox.isChecked() is False
    assert window.crop_to_content_checkbox.isEnabled() is False
    assert window.fg_threshold_value_label.text() == "240"
    assert window.bg_threshold_value_label.text() == "10"
    assert window.erode_size_value_label.text() == "10"

    window.fg_threshold_slider.setValue(200)
    window.bg_threshold_slider.setValue(30)
    window.erode_size_slider.setValue(7)
    assert window.fg_threshold_value_label.text() == "200"
    assert window.bg_threshold_value_label.text() == "30"
    assert window.erode_size_value_label.text() == "7"

    params = window._collect_background_removal_params()
    assert params.fg_threshold == 200
    assert params.bg_threshold == 30
    assert params.erode_size == 7
    assert params.crop_to_content is False
    window.close()


def test_collect_background_removal_params_enables_crop_only_for_image(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    image_path = tmp_path / "portrait.png"
    Image.new("RGBA", (40, 20), (255, 255, 255, 255)).save(image_path)
    window._load_image_file(image_path)
    window.crop_to_content_checkbox.setChecked(True)

    image_params = window._collect_background_removal_params()

    window.state.media_kind = MediaKind.VIDEO
    video_params = window._collect_background_removal_params()

    assert image_params.crop_to_content is True
    assert video_params.crop_to_content is False
    window.close()


def test_preview_background_is_shared_with_animation_dialog(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    atlas_path = tmp_path / "spritesheet.png"
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    assert pixmap.save(str(atlas_path), "PNG")

    window.state.atlas_path = atlas_path
    window._preview_atlas_params = AtlasParams(
        columns=1,
        rows=1,
        frame_width=32,
        frame_height=32,
        resize_mode=ResizeMode.FIT,
    )
    window._preview_frame_count = 1

    window.preview_background_combo.setCurrentText("White")
    window._open_spritesheet_preview()

    dialog = window._spritesheet_preview_dialog
    assert dialog is not None
    assert "background: #ffffff;" in window.atlas_preview_label.styleSheet()
    assert "background: #ffffff;" in dialog.preview_label.styleSheet()

    window.preview_background_combo.setCurrentText("Green")
    assert "background: #00ff00;" in window.atlas_preview_label.styleSheet()
    assert "background: #00ff00;" in dialog.preview_label.styleSheet()
    window.close()


def test_extract_auto_triggers_build_spritesheet() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    window.auto_remove_checkbox.setChecked(False)
    window._on_extract_completed([Path("frame_000001.png")])

    calls: list[str] = []

    def _fake_build() -> None:
        calls.append("build")

    window._build_spritesheet = _fake_build  # type: ignore[method-assign]
    worker = TaskWorker(lambda progress_cb: None)
    window._on_worker_finished(worker)

    assert calls == ["build"]
    assert window._auto_build_pending is False
    window.close()


def test_extract_auto_remove_then_auto_build_spritesheet() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    window.auto_remove_checkbox.setChecked(True)
    window._on_extract_completed([Path("frame_000001.png")])

    calls: list[str] = []

    def _fake_remove() -> None:
        calls.append("remove")

    def _fake_build() -> None:
        calls.append("build")

    window._remove_background = _fake_remove  # type: ignore[method-assign]
    window._build_spritesheet = _fake_build  # type: ignore[method-assign]

    first_worker = TaskWorker(lambda progress_cb: None)
    second_worker = TaskWorker(lambda progress_cb: None)
    window._on_worker_finished(first_worker)
    window._on_worker_finished(second_worker)

    assert calls == ["remove", "build"]
    assert window._auto_remove_pending is False
    assert window._auto_build_pending is False
    window.close()
