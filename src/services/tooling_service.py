from __future__ import annotations

import importlib
import shutil
from typing import Any
from collections.abc import Callable


class ToolingService:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self._rembg_default_model_name = "isnet-anime"
        self._rembg_session: Any | None = None
        self._rembg_session_model_name: str | None = None

    def ensure_ffmpeg_tools(self) -> None:
        if shutil.which(self.ffmpeg_bin) is None:
            raise RuntimeError("FFmpeg не найден. Установите ffmpeg и добавьте его в PATH")
        if shutil.which(self.ffprobe_bin) is None:
            raise RuntimeError("FFprobe не найден. Установите ffprobe и добавьте его в PATH")

    def ensure_rembg_remove(self) -> Callable[..., bytes]:
        try:
            rembg_module = importlib.import_module("rembg")
        except ModuleNotFoundError as exc:
            raise RuntimeError("rembg не найден. Установите пакет rembg") from exc

        try:
            importlib.import_module("onnxruntime")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Для rembg не найден backend onnxruntime. "
                "Установите CPU-вариант: pip install \"rembg[cpu]\""
            ) from exc

        remove_fn = getattr(rembg_module, "remove", None)
        if remove_fn is None:
            raise RuntimeError("В пакете rembg отсутствует функция remove")
        return remove_fn

    def ensure_rembg_session(self, model_name: str | None = None) -> Any:
        try:
            rembg_module = importlib.import_module("rembg")
        except ModuleNotFoundError as exc:
            raise RuntimeError("rembg не найден. Установите пакет rembg") from exc

        try:
            importlib.import_module("onnxruntime")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Для rembg не найден backend onnxruntime. "
                "Установите CPU-вариант: pip install \"rembg[cpu]\""
            ) from exc

        new_session_fn = getattr(rembg_module, "new_session", None)
        if new_session_fn is None:
            raise RuntimeError("В пакете rembg отсутствует функция new_session")

        target_model = model_name or self._rembg_default_model_name
        if self._rembg_session is not None and self._rembg_session_model_name == target_model:
            return self._rembg_session

        try:
            self._rembg_session = new_session_fn(model_name=target_model)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Не удалось инициализировать модель rembg '{target_model}': {exc}") from exc

        self._rembg_session_model_name = target_model
        return self._rembg_session
