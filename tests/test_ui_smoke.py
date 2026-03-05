import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

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
