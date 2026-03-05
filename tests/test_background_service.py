from pathlib import Path

import pytest
from PIL import Image

from src.models import BackgroundRemovalParams
from src.services.background_service import BackgroundService
from src.services.tooling_service import ToolingService


class _FakeToolingService(ToolingService):
    def __init__(self, result_bytes: bytes) -> None:
        super().__init__()
        self.result_bytes = result_bytes
        self.calls: list[dict[str, object]] = []

    def ensure_rembg_remove(self):
        def _remove(source_bytes: bytes, **kwargs):
            self.calls.append({"source_bytes": source_bytes, "kwargs": kwargs})
            return self.result_bytes

        return _remove


def test_remove_background_batch_uses_non_alpha_matting_with_post_process(tmp_path: Path) -> None:
    source_dir = tmp_path / "frames"
    cut_dir = tmp_path / "cut"
    source_dir.mkdir(parents=True, exist_ok=True)

    source = source_dir / "frame_001.png"
    Image.new("RGBA", (16, 16), (255, 255, 255, 255)).save(source)
    result_bytes = source.read_bytes()

    fake_tooling = _FakeToolingService(result_bytes)
    service = BackgroundService(fake_tooling)
    params = BackgroundRemovalParams(fg_threshold=230, bg_threshold=20, erode_size=5)

    output_files = service.remove_background_batch([source], cut_dir, params=params)

    assert len(output_files) == 1
    assert len(fake_tooling.calls) == 1
    kwargs = fake_tooling.calls[0]["kwargs"]
    assert kwargs["alpha_matting"] is False
    assert kwargs["post_process_mask"] is True


def test_background_removal_params_erode_size_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="Erode Size"):
        BackgroundRemovalParams(fg_threshold=240, bg_threshold=10, erode_size=-1).validate()
