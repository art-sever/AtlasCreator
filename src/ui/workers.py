from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    progress = Signal(int, str)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class TaskWorker(QRunnable):
    def __init__(self, task: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        # Отключаем автоудаление, чтобы жизненным циклом управлял UI-слой.
        self.setAutoDelete(False)
        self.task = task
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def _safe_emit(self, signal: Any, *args: Any) -> None:
        try:
            signal.emit(*args)
        except Exception:  # noqa: BLE001
            # На этапе закрытия приложения Qt-объекты могут быть уже удалены.
            # В этом случае пропускаем сигнал, чтобы не ронять поток.
            return

    @Slot()
    def run(self) -> None:
        def _progress(value: int, message: str) -> None:
            clamped = max(0, min(100, int(value)))
            self._safe_emit(self.signals.progress, clamped, message)

        try:
            result = self.task(*self.args, progress_cb=_progress, **self.kwargs)
            self._safe_emit(self.signals.result, result)
        except Exception as exc:  # noqa: BLE001
            self._safe_emit(self.signals.error, str(exc))
        finally:
            self._safe_emit(self.signals.finished)
