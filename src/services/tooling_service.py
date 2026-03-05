from __future__ import annotations

import importlib
import shutil
from collections.abc import Callable


class ToolingService:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def ensure_ffmpeg_tools(self) -> None:
        if shutil.which(self.ffmpeg_bin) is None:
            raise RuntimeError("FFmpeg не найден. Установите ffmpeg и добавьте его в PATH")
        if shutil.which(self.ffprobe_bin) is None:
            raise RuntimeError("FFprobe не найден. Установите ffprobe и добавьте его в PATH")

    def ensure_rembg_remove(self) -> Callable[[bytes], bytes]:
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
