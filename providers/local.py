from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from providers.base import DownloadedAsset


@dataclass(frozen=True)
class LocalAudioProvider:
    """Uses an existing local MP3 by track_id or copies from a provided file path."""

    track_file: str | None = None

    def ensure_audio(self, *, track_id: str, dest_dir: str) -> DownloadedAsset:
        dest = Path(dest_dir) / f"{track_id}.mp3"
        if dest.exists():
            return DownloadedAsset(path=str(dest.resolve()), source="local:existing")

        if not self.track_file:
            raise FileNotFoundError(
                f"Missing audio track {dest}. Provide --online-track-file or place it in {dest_dir}."
            )

        src = Path(self.track_file)
        if not src.exists():
            raise FileNotFoundError(f"Audio file not found: {src}")

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return DownloadedAsset(path=str(dest.resolve()), source=f"local:file:{src}")


@dataclass(frozen=True)
class LocalVideoProvider:
    """Uses existing local videos from a directory (no downloading)."""

    def ensure_videos(self, *, query: str, dest_dir: str, min_count: int) -> list[DownloadedAsset]:
        _ = query
        p = Path(dest_dir)
        if not p.exists():
            return []

        exts = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
        files = [f for f in sorted(p.glob("**/*")) if f.is_file() and f.suffix.lower() in exts]
        assets = [DownloadedAsset(path=str(f.resolve()), source="local:dir") for f in files]
        if len(assets) < min_count:
            raise RuntimeError(
                f"Not enough local videos in {dest_dir} (found {len(assets)}, need {min_count})."
            )
        return assets
