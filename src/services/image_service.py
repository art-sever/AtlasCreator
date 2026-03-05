from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageOps

from src.models import ResizeMode

ProgressCallback = Callable[[int, str], None]


class ImageService:
    def resize_frame_rgba(self, image: Image.Image, width: int, height: int, mode: ResizeMode) -> Image.Image:
        if width <= 0 or height <= 0:
            raise ValueError("Некорректный размер кадра")

        rgba_image = image.convert("RGBA")
        target_size = (width, height)

        if mode == ResizeMode.STRETCH:
            return rgba_image.resize(target_size, Image.Resampling.LANCZOS)

        if mode == ResizeMode.CROP_CENTER:
            return ImageOps.fit(
                rgba_image,
                target_size,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )

        # FIT: вписываем изображение с сохранением пропорций в прозрачный холст.
        fitted = rgba_image.copy()
        fitted.thumbnail(target_size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
        offset_x = (width - fitted.width) // 2
        offset_y = (height - fitted.height) // 2
        canvas.paste(fitted, (offset_x, offset_y), fitted)
        return canvas

    def prepare_frames(
        self,
        frame_paths: list[Path],
        width: int,
        height: int,
        mode: ResizeMode,
        progress_cb: ProgressCallback | None = None,
    ) -> list[Image.Image]:
        if not frame_paths:
            raise ValueError("Список кадров пуст")

        callback = progress_cb or (lambda _value, _message: None)
        prepared: list[Image.Image] = []
        total = len(frame_paths)

        for index, frame_path in enumerate(frame_paths, start=1):
            with Image.open(frame_path) as image:
                prepared.append(self.resize_frame_rgba(image, width, height, mode))
            callback(int(index * 100 / total), "Подготовка кадров")

        return prepared
