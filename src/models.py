from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ExtractMode(str, Enum):
    TARGET_FPS = "target_fps"
    EXACT_COUNT = "exact_count"


class ResizeMode(str, Enum):
    FIT = "fit"
    CROP_CENTER = "crop_center"
    STRETCH = "stretch"


class MediaKind(str, Enum):
    VIDEO = "video"
    IMAGE = "image"


@dataclass
class VideoMeta:
    path: Path
    duration_sec: float
    fps: float
    width: int
    height: int
    frame_count_estimate: int


@dataclass
class ExtractionParams:
    mode: ExtractMode
    target_fps: float | None = None
    exact_count: int | None = None

    def validate(self) -> None:
        if self.mode == ExtractMode.TARGET_FPS:
            if self.target_fps is None or self.target_fps <= 0:
                raise ValueError("Невалидный FPS: значение должно быть больше 0")
            return
        if self.mode == ExtractMode.EXACT_COUNT:
            if self.exact_count is None or self.exact_count <= 0:
                raise ValueError("Невалидное количество кадров: значение должно быть больше 0")
            return
        raise ValueError("Неизвестный режим извлечения кадров")


@dataclass
class BackgroundRemovalParams:
    fg_threshold: int = 240
    bg_threshold: int = 10
    erode_size: int = 10
    crop_to_content: bool = False

    def validate(self) -> None:
        if not 0 <= self.fg_threshold <= 255:
            raise ValueError("FG Threshold должен быть в диапазоне 0..255")
        if not 0 <= self.bg_threshold <= 255:
            raise ValueError("BG Threshold должен быть в диапазоне 0..255")
        if self.erode_size < 0:
            raise ValueError("Erode Size должен быть больше или равен 0")


@dataclass
class AtlasParams:
    columns: int
    rows: int
    frame_width: int
    frame_height: int
    resize_mode: ResizeMode

    @property
    def capacity(self) -> int:
        return self.columns * self.rows

    @property
    def sheet_width(self) -> int:
        return self.columns * self.frame_width

    @property
    def sheet_height(self) -> int:
        return self.rows * self.frame_height

    def validate(self) -> None:
        if self.columns <= 0:
            raise ValueError("Некорректное значение Columns")
        if self.rows <= 0:
            raise ValueError("Некорректное значение Rows")
        if self.frame_width <= 0:
            raise ValueError("Некорректное значение Frame Width")
        if self.frame_height <= 0:
            raise ValueError("Некорректное значение Frame Height")
