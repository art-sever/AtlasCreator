import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from src.models import AtlasParams, ExtractMode, ExtractionParams, ResizeMode
from src.services.atlas_service import AtlasService
from src.services.background_service import BackgroundService
from src.services.image_service import ImageService
from src.services.tooling_service import ToolingService
from src.services.video_service import VideoService


pytestmark = pytest.mark.integration


def _has_ffmpeg_tools() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _build_test_video(video_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=96x96:rate=24",
        "-t",
        "1.0",
        str(video_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)


@pytest.mark.skipif(not _has_ffmpeg_tools(), reason="ffmpeg/ffprobe недоступны")
def test_extract_frames_target_fps(tmp_path: Path) -> None:
    video_path = tmp_path / "input.mp4"
    out_dir = tmp_path / "frames"
    _build_test_video(video_path)

    service = VideoService()
    params = ExtractionParams(mode=ExtractMode.TARGET_FPS, target_fps=8.0)
    frames = service.extract_frames(video_path, params, out_dir)

    assert len(frames) > 0
    assert all(frame.exists() for frame in frames)


@pytest.mark.skipif(not _has_ffmpeg_tools(), reason="ffmpeg/ffprobe недоступны")
def test_extract_frames_exact_count_8(tmp_path: Path) -> None:
    video_path = tmp_path / "input.mp4"
    out_dir = tmp_path / "frames"
    _build_test_video(video_path)

    service = VideoService()
    params = ExtractionParams(mode=ExtractMode.EXACT_COUNT, exact_count=8)
    frames = service.extract_frames(video_path, params, out_dir)

    assert len(frames) == 8
    assert all(frame.exists() for frame in frames)


def test_build_spritesheet_2048x1024(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    frame_paths: list[Path] = []
    for index in range(8):
        frame_path = frames_dir / f"frame_{index:03d}.png"
        Image.new("RGBA", (256, 256), (index * 20, 30, 120, 255)).save(frame_path)
        frame_paths.append(frame_path)

    image_service = ImageService()
    atlas_service = AtlasService()
    params = AtlasParams(columns=4, rows=2, frame_width=512, frame_height=512, resize_mode=ResizeMode.FIT)
    resized_frames = image_service.prepare_frames(frame_paths, 512, 512, ResizeMode.FIT)

    out_path = tmp_path / "spritesheet.png"
    atlas_service.build_spritesheet(resized_frames, params, out_path)

    with Image.open(out_path) as sheet:
        assert sheet.size == (2048, 1024)
        assert sheet.mode == "RGBA"


def test_remove_background_rgba_output(tmp_path: Path) -> None:
    pytest.importorskip("rembg")

    source_dir = tmp_path / "src"
    cut_dir = tmp_path / "cut"
    source_dir.mkdir(parents=True, exist_ok=True)

    source = source_dir / "frame_001.png"
    image = Image.new("RGBA", (128, 128), (255, 255, 255, 255))
    image.paste((0, 0, 0, 255), (32, 32, 96, 96))
    image.save(source)

    service = BackgroundService(ToolingService())
    try:
        result = service.remove_background_batch([source], cut_dir)
    except RuntimeError as exc:
        pytest.skip(f"rembg недоступен в текущей среде: {exc}")

    assert len(result) == 1
    with Image.open(result[0]) as output:
        assert output.mode == "RGBA"
