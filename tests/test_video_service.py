from pathlib import Path

from src.services.video_service import VideoService


def test_parse_ffprobe_payload() -> None:
    payload = {
        "streams": [
            {
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "nb_frames": "120",
            }
        ],
        "format": {"duration": "4.0"},
    }

    meta = VideoService.parse_ffprobe_payload(payload, Path("/tmp/sample.mp4"))

    assert meta.width == 1920
    assert meta.height == 1080
    assert round(meta.fps, 3) == round(30000 / 1001, 3)
    assert meta.duration_sec == 4.0
    assert meta.frame_count_estimate == 120


def test_build_even_frame_indices_for_single_frame() -> None:
    indices = VideoService.build_even_frame_indices(total_frames=100, exact_count=1)
    assert indices == [0]


def test_build_even_frame_indices_for_many_frames() -> None:
    indices = VideoService.build_even_frame_indices(total_frames=120, exact_count=8)

    assert len(indices) == 8
    assert indices[0] == 0
    assert indices[-1] == 119
    assert all(indices[i] < indices[i + 1] for i in range(len(indices) - 1))


def test_build_even_frame_indices_raises_when_count_exceeds_total() -> None:
    try:
        VideoService.build_even_frame_indices(total_frames=4, exact_count=8)
    except ValueError as exc:
        assert "больше" in str(exc)
    else:
        raise AssertionError("Ожидался ValueError при exact_count > total_frames")
