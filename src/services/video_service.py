from __future__ import annotations

import json
import math
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from src.models import ExtractMode, ExtractionParams, VideoMeta

ProgressCallback = Callable[[int, str], None]


class VideoService:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def get_metadata(self, video_path: Path) -> VideoMeta:
        cmd = [
            self.ffprobe_bin,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            error_text = completed.stderr.strip() or "неизвестная ошибка ffprobe"
            raise RuntimeError(f"Не удалось получить метаданные видео: {error_text}")

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("FFprobe вернул некорректный JSON") from exc

        return self.parse_ffprobe_payload(payload, video_path)

    @staticmethod
    def parse_ffprobe_payload(payload: dict, video_path: Path) -> VideoMeta:
        streams = payload.get("streams") or []
        if not streams:
            raise RuntimeError("Видеопоток не найден")

        stream = streams[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        fps = VideoService._parse_fps(str(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"))

        format_info = payload.get("format") or {}
        duration_sec = float(format_info.get("duration") or 0.0)
        nb_frames_value = stream.get("nb_frames")

        if isinstance(nb_frames_value, str) and nb_frames_value.isdigit():
            frame_count_estimate = int(nb_frames_value)
        else:
            frame_count_estimate = int(round(duration_sec * fps)) if duration_sec > 0 and fps > 0 else 0

        return VideoMeta(
            path=video_path,
            duration_sec=duration_sec,
            fps=fps,
            width=width,
            height=height,
            frame_count_estimate=frame_count_estimate,
        )

    @staticmethod
    def _parse_fps(ratio: str) -> float:
        if "/" in ratio:
            num_text, den_text = ratio.split("/", 1)
            try:
                num = float(num_text)
                den = float(den_text)
                return num / den if den else 0.0
            except ValueError:
                return 0.0
        try:
            return float(ratio)
        except ValueError:
            return 0.0

    def extract_frames(
        self,
        video_path: Path,
        params: ExtractionParams,
        out_dir: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> list[Path]:
        params.validate()
        self._prepare_output_dir(out_dir)

        callback = progress_cb or (lambda _value, _message: None)
        callback(0, "Запуск извлечения кадров")

        if params.mode == ExtractMode.TARGET_FPS:
            frames = self._extract_frames_target_fps(video_path, float(params.target_fps), out_dir, callback)
        else:
            frames = self._extract_frames_exact_count(video_path, int(params.exact_count), out_dir, callback)

        if not frames:
            raise RuntimeError("FFmpeg не извлек ни одного кадра")

        callback(100, "Извлечение кадров завершено")
        return frames

    def _extract_frames_target_fps(
        self,
        video_path: Path,
        target_fps: float,
        out_dir: Path,
        progress_cb: ProgressCallback,
    ) -> list[Path]:
        metadata = self.get_metadata(video_path)
        duration = max(metadata.duration_sec, 0.001)
        output_pattern = out_dir / "frame_%06d.png"
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={target_fps}",
            "-progress",
            "pipe:1",
            "-nostats",
            str(output_pattern),
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        last_progress = 0
        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("out_time_ms="):
                    try:
                        out_time_ms = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    ratio = min(out_time_ms / (duration * 1_000_000), 1.0)
                    progress_value = min(99, max(last_progress, int(ratio * 100)))
                    if progress_value != last_progress:
                        last_progress = progress_value
                        progress_cb(progress_value, "Извлечение кадров через Target FPS")

        stderr_text = process.stderr.read() if process.stderr is not None else ""
        return_code = process.wait()
        if return_code != 0:
            error_text = stderr_text.strip() or "неизвестная ошибка ffmpeg"
            raise RuntimeError(f"FFmpeg завершился с ошибкой: {error_text}")

        return sorted(out_dir.glob("frame_*.png"))

    def _extract_frames_exact_count(
        self,
        video_path: Path,
        exact_count: int,
        out_dir: Path,
        progress_cb: ProgressCallback,
    ) -> list[Path]:
        total_frames = self.get_total_frames(video_path)
        if total_frames <= 0:
            metadata = self.get_metadata(video_path)
            total_frames = metadata.frame_count_estimate
        if total_frames <= 0:
            raise RuntimeError("Не удалось определить количество кадров в видео")

        frame_indices = self.build_even_frame_indices(total_frames, exact_count)
        select_filter = self._build_select_filter(frame_indices)
        output_pattern = out_dir / "frame_%06d.png"

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i",
            str(video_path),
            "-vf",
            select_filter,
            "-vsync",
            "0",
            "-progress",
            "pipe:1",
            "-nostats",
            "-loglevel",
            "error",
            str(output_pattern),
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        last_progress = 0
        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("frame="):
                    try:
                        extracted = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    progress_value = min(99, max(last_progress, int(extracted * 100 / exact_count)))
                    if progress_value != last_progress:
                        last_progress = progress_value
                        progress_cb(progress_value, "Извлечение кадров по точному количеству")

        stderr_text = process.stderr.read() if process.stderr is not None else ""
        return_code = process.wait()
        if return_code != 0:
            error_text = stderr_text.strip() or "неизвестная ошибка ffmpeg"
            raise RuntimeError(f"Не удалось извлечь кадры по точному количеству: {error_text}")

        frames = sorted(out_dir.glob("frame_*.png"), key=self.parse_frame_index_from_filename)
        if len(frames) != exact_count:
            raise RuntimeError(
                f"Ожидалось ровно {exact_count} кадров, но извлечено {len(frames)}. "
                "Проверьте исходное видео или уменьшите Exact Frame Count."
            )
        return frames

    @staticmethod
    def build_even_frame_indices(total_frames: int, exact_count: int) -> list[int]:
        if exact_count <= 0:
            raise ValueError("exact_count должен быть больше 0")
        if total_frames <= 0:
            raise ValueError("total_frames должен быть больше 0")
        if exact_count > total_frames:
            raise ValueError(
                f"Запрошено кадров ({exact_count}) больше, чем есть в видео ({total_frames})"
            )
        if exact_count == 1:
            return [0]

        step = (total_frames - 1) / (exact_count - 1)
        indices = [int(round(index * step)) for index in range(exact_count)]

        unique_indices: list[int] = []
        for idx in indices:
            if unique_indices and idx <= unique_indices[-1]:
                idx = unique_indices[-1] + 1
            unique_indices.append(min(idx, total_frames - 1))

        # Страхуем монотонность после ограничения верхней границы.
        for i in range(len(unique_indices) - 2, -1, -1):
            max_allowed = unique_indices[i + 1] - 1
            unique_indices[i] = min(unique_indices[i], max_allowed)
            unique_indices[i] = max(unique_indices[i], 0)

        return unique_indices

    def get_total_frames(self, video_path: Path) -> int:
        cmd = [
            self.ffprobe_bin,
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames,nb_frames",
            "-of",
            "json",
            str(video_path),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return 0

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return 0

        streams = payload.get("streams") or []
        if not streams:
            return 0

        stream = streams[0]
        nb_read_frames = stream.get("nb_read_frames")
        nb_frames = stream.get("nb_frames")

        for value in (nb_read_frames, nb_frames):
            if isinstance(value, str) and value.isdigit():
                return int(value)
            if isinstance(value, (int, float)) and value > 0:
                return int(math.floor(value))
        return 0

    @staticmethod
    def _build_select_filter(frame_indices: list[int]) -> str:
        terms = [f"eq(n\\,{frame_idx})" for frame_idx in frame_indices]
        return f"select={'+'.join(terms)}"

    @staticmethod
    def _prepare_output_dir(out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for png_file in out_dir.glob("*.png"):
            png_file.unlink()

    @staticmethod
    def parse_frame_index_from_filename(frame_path: Path) -> int:
        match = re.search(r"(\d+)", frame_path.stem)
        if not match:
            return 10**12
        return int(match.group(1))
