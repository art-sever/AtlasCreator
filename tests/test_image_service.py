from PIL import Image

from src.models import ResizeMode
from src.services.image_service import ImageService


def _build_source_image() -> Image.Image:
    image = Image.new("RGBA", (200, 100), (255, 0, 0, 255))
    return image


def test_resize_fit_keeps_canvas_size() -> None:
    service = ImageService()
    source = _build_source_image()

    resized = service.resize_frame_rgba(source, 128, 128, ResizeMode.FIT)

    assert resized.size == (128, 128)
    assert resized.mode == "RGBA"


def test_resize_crop_center_keeps_canvas_size() -> None:
    service = ImageService()
    source = _build_source_image()

    resized = service.resize_frame_rgba(source, 64, 64, ResizeMode.CROP_CENTER)

    assert resized.size == (64, 64)
    assert resized.mode == "RGBA"


def test_resize_stretch_keeps_canvas_size() -> None:
    service = ImageService()
    source = _build_source_image()

    resized = service.resize_frame_rgba(source, 80, 120, ResizeMode.STRETCH)

    assert resized.size == (80, 120)
    assert resized.mode == "RGBA"
