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

    assert window.count_spin.isVisible()
    assert not window.fps_spin.isVisible()
    window.close()
