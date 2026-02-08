from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PostSpec:
    post_dir: str
    caption: str
    hashtags: str
    track_id: str
    themes: list[str]
    lyrics_offset: float = 0.0


def parse_caption_file(post_dir: str) -> PostSpec:
    p_spec = Path(post_dir) / "caption_spec.txt"
    p = p_spec if p_spec.exists() else (Path(post_dir) / "caption.txt")
    if not p.exists():
        raise FileNotFoundError(f"Missing caption_spec.txt or caption.txt: {p}")

    lines = p.read_text(encoding="utf-8").splitlines()
    lines = [ln.strip() for ln in lines if ln.strip() != ""]
    if len(lines) < 4:
        raise ValueError(f"Spec file must have at least 4 non-empty lines: {p}")

    caption = lines[0]
    hashtags = lines[1]

    track_id = ""
    themes = []
    lyrics_offset = 0.0

    for line in lines[2:]:
        if line.lower().startswith("track_id="):
            track_id = line.split("=", 1)[1].strip()
        elif line.lower().startswith("themes="):
            themes_raw = line.split("=", 1)[1].strip()
            themes = [t.strip() for t in themes_raw.split(",") if t.strip()]
        elif line.lower().startswith("lyrics_offset="):
            try:
                lyrics_offset = float(line.split("=", 1)[1].strip())
            except ValueError:
                pass

    if not track_id:
        raise ValueError(f"Missing track_id=<id> in {p}")
    if not themes:
        raise ValueError(f"themes must not be empty in {p}")

    return PostSpec(
        post_dir=str(Path(post_dir).resolve()),
        caption=caption,
        hashtags=hashtags,
        track_id=track_id,
        themes=themes,
        lyrics_offset=lyrics_offset
    )
