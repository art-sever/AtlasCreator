from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image

from src.models import BackgroundRemovalParams
from src.services.tooling_service import ToolingService

ProgressCallback = Callable[[int, str], None]


class BackgroundService:
    def __init__(self, tooling_service: ToolingService) -> None:
        self.tooling_service = tooling_service

    def remove_background_batch(
        self,
        input_frames: list[Path],
        out_dir: Path,
        params: BackgroundRemovalParams | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> list[Path]:
        if not input_frames:
            raise ValueError("Нет кадров для удаления фона")

        remove_fn = self.tooling_service.ensure_rembg_remove()
        removal_params = params or BackgroundRemovalParams()
        removal_params.validate()
        callback = progress_cb or (lambda _value, _message: None)

        out_dir.mkdir(parents=True, exist_ok=True)
        for png_file in out_dir.glob("*.png"):
            png_file.unlink()

        output_files: list[Path] = []
        total = len(input_frames)

        for index, frame_path in enumerate(input_frames, start=1):
            with frame_path.open("rb") as src_file:
                source_bytes = src_file.read()

            # Для спрайтов используем базовую маску без alpha matting и включаем post-process очистку.
            try:
                result_bytes = remove_fn(
                    source_bytes,
                    alpha_matting=False,
                    post_process_mask=True,
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Ошибка rembg при обработке {frame_path.name}: {exc}") from exc

            out_path = out_dir / frame_path.name
            with out_path.open("wb") as dst_file:
                dst_file.write(result_bytes)

            with Image.open(out_path) as image:
                rgba_image = image.convert("RGBA")
                rgba_image.save(out_path, format="PNG")

            output_files.append(out_path)
            callback(int(index * 100 / total), "Удаление фона")

        return output_files
