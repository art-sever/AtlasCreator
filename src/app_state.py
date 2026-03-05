from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.models import VideoMeta


@dataclass
class AppState:
    project_root: Path
    temp_dir: Path
    frames_dir: Path
    cut_dir: Path
    output_dir: Path
    preview_dir: Path
    video_path: Path | None = None
    video_meta: VideoMeta | None = None
    extracted_frames: list[Path] = field(default_factory=list)
    cut_frames: list[Path] = field(default_factory=list)
    atlas_path: Path | None = None

    @classmethod
    def create(cls, project_root: Path) -> "AppState":
        temp_dir = project_root / "temp"
        return cls(
            project_root=project_root,
            temp_dir=temp_dir,
            frames_dir=temp_dir / "frames",
            cut_dir=temp_dir / "cut",
            output_dir=temp_dir / "output",
            preview_dir=temp_dir / "preview",
        )

    def reset_pipeline_outputs(self) -> None:
        self.extracted_frames = []
        self.cut_frames = []
        self.atlas_path = None

    def prepare_temp_dirs(self, clean: bool = False) -> None:
        targets = [self.frames_dir, self.cut_dir, self.output_dir, self.preview_dir]
        for target in targets:
            if clean and target.exists():
                for child in target.iterdir():
                    if child.is_file():
                        child.unlink()
            target.mkdir(parents=True, exist_ok=True)
