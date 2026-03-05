import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.models import AtlasParams, ResizeMode  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402


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


def test_spritesheet_video_preview_button_initially_disabled() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.preview_video_button.text() == "Video Preview"
    assert not window.preview_video_button.isEnabled()
    window.close()


def test_preview_background_selector_has_expected_options() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    options = [window.preview_background_combo.itemText(idx) for idx in range(window.preview_background_combo.count())]
    assert options == ["Black", "White", "Green"]
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
