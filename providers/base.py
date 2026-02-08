from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DownloadedAsset:
    path: str
    source: str


class VideoProvider(Protocol):
    def ensure_videos(self, *, query: str, dest_dir: str, min_count: int) -> list[DownloadedAsset]:
        """Ensure at least min_count videos exist in dest_dir for the query."""


class AudioProvider(Protocol):
    def ensure_audio(self, *, track_id: str, dest_dir: str) -> DownloadedAsset:
        """Ensure audio track exists in dest_dir as <track_id>.mp3."""
