from pathlib import Path

import pytest
from PIL import Image

from src.models import AtlasParams, ResizeMode
from src.services.atlas_service import AtlasService


def _frame(color: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", (32, 32), color)


def test_build_spritesheet_size(tmp_path: Path) -> None:
    service = AtlasService()
    frames = [_frame((255, 0, 0, 255)), _frame((0, 255, 0, 255)), _frame((0, 0, 255, 255))]
    params = AtlasParams(columns=2, rows=2, frame_width=32, frame_height=32, resize_mode=ResizeMode.FIT)

    out_path = tmp_path / "spritesheet.png"
    built_path = service.build_spritesheet(frames, params, out_path)

    assert built_path.exists()
    with Image.open(built_path) as image:
        assert image.size == (64, 64)
        assert image.mode == "RGBA"


def test_build_spritesheet_raises_on_capacity_overflow(tmp_path: Path) -> None:
    service = AtlasService()
    frames = [_frame((255, 0, 0, 255)) for _ in range(5)]
    params = AtlasParams(columns=2, rows=2, frame_width=32, frame_height=32, resize_mode=ResizeMode.FIT)

    with pytest.raises(ValueError, match="вместимость"):
        service.build_spritesheet(frames, params, tmp_path / "sheet.png")
