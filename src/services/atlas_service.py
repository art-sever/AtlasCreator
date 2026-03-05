from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image

from src.models import AtlasParams

ProgressCallback = Callable[[int, str], None]


class AtlasService:
    def build_spritesheet(
        self,
        frames: list[Image.Image],
        atlas_params: AtlasParams,
        out_path: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> Path:
        atlas_params.validate()
        if not frames:
            raise ValueError("Нет кадров для сборки spritesheet")
        if len(frames) > atlas_params.capacity:
            raise ValueError("Число кадров больше, чем вместимость atlas")

        callback = progress_cb or (lambda _value, _message: None)
        spritesheet = Image.new(
            "RGBA",
            (atlas_params.sheet_width, atlas_params.sheet_height),
            (0, 0, 0, 0),
        )

        total = len(frames)
        for index, frame in enumerate(frames):
            row = index // atlas_params.columns
            col = index % atlas_params.columns
            x = col * atlas_params.frame_width
            y = row * atlas_params.frame_height

            rgba_frame = frame.convert("RGBA")
            spritesheet.paste(rgba_frame, (x, y), rgba_frame)
            callback(int((index + 1) * 100 / total), "Сборка spritesheet")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        spritesheet.save(out_path, format="PNG")
        return out_path
