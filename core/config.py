from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenderConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    min_duration_s: float = 5.0
    max_duration_s: float = 9.0  # 8-10s target (randomized per video)

    clip_min_s: float = 0.25  # Faster cuts
    clip_max_s: float = 0.8   # Faster cuts

    speed_min: float = 0.95  # Less speed variation = simpler processing
    speed_max: float = 1.05

    # Visual style
    contrast: float = 1.18
    saturation: float = 0.86
    brightness: float = -0.02
    gamma: float = 1.02
    enable_grain: bool = True
    grain_strength: int = 6

    # Encoding
    video_bitrate: str = "14M"
    maxrate: str = "18M"
    bufsize: str = "28M"

    # NVENC presets: p1 (fastest) .. p7 (slowest/best quality)
    # p1 = muito rápido, p3 = balanced, p5 = slow/high quality
    nvenc_preset: str = "p1"  # Fastest for real-time encoding

    # Safe Area Guidelines (TikTok 9:16)
    margin_lateral: float = 0.10  # 10%
    margin_bottom: float = 0.15   # 15%
    margin_top: float = 0.08      # 8-10%


@dataclass(frozen=True)
class PathsConfig:
    project_root: str
    broll_dir: str
    posts_dir: str
    audio_dir: str
    tools_dir: str
    mediahuman_dir: str = "/Users/caioalbanese/Music/Downloaded by MediaHuman"

    def with_resolved_paths(self) -> PathsConfig:
        """Return a new config with all paths resolved to absolute paths."""
        p_root = Path(self.project_root).resolve()
        return PathsConfig(
            project_root=str(p_root),
            broll_dir=str((p_root / self.broll_dir).resolve()) if not Path(self.broll_dir).is_absolute() else self.broll_dir,
            posts_dir=str((p_root / self.posts_dir).resolve()) if not Path(self.posts_dir).is_absolute() else self.posts_dir,
            audio_dir=str((p_root / self.audio_dir).resolve()) if not Path(self.audio_dir).is_absolute() else self.audio_dir,
            tools_dir=str((p_root / self.tools_dir).resolve()) if not Path(self.tools_dir).is_absolute() else self.tools_dir,
            mediahuman_dir=self.mediahuman_dir
        )
