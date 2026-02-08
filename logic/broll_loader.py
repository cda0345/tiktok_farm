from __future__ import annotations

import json
import os
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from core.ffmpeg_utils import ffprobe_json, run_ffmpeg, safe_relpath


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@dataclass
class ClipMeta:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    motion: float


class BrollLibrary:
    def __init__(
        self,
        broll_dir: str,
        ffmpeg_path: str,
        ffprobe_path: str,
        cache_path: str | None = None,
    ) -> None:
        self.broll_dir = str(Path(broll_dir).resolve())
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.cache_path = cache_path or str(Path(self.broll_dir) / "_cache.json")
        self._cache: dict[str, dict] = {}
        self._metas: dict[str, ClipMeta] = {}

        self._load_cache()

    def _load_cache(self) -> None:
        p = Path(self.cache_path)
        if p.exists():
            try:
                self._cache = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}

    def _save_cache(self) -> None:
        p = Path(self.cache_path)
        p.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def _iter_theme_files(self, theme: str) -> Iterable[str]:
        theme_dir = Path(self.broll_dir) / theme
        if not theme_dir.exists():
            return
        for p in theme_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in (VIDEO_EXTS | IMAGE_EXTS):
                yield str(p.resolve())

    def _probe_meta(self, path: str) -> ClipMeta:
        p = Path(path)
        try:
            st = p.stat()
            size = int(st.st_size)
            mtime_ns = int(st.st_mtime_ns)
        except Exception:
            size = -1
            mtime_ns = -1

        cached = self._cache.get(path)
        if isinstance(cached, dict) and cached.get("size") == size and cached.get("mtime_ns") == mtime_ns:
            try:
                return ClipMeta(
                    path=path,
                    duration=float(cached.get("duration") or 0.0),
                    width=int(cached.get("width") or 0),
                    height=int(cached.get("height") or 0),
                    fps=float(cached.get("fps") or 0.0),
                    motion=float(cached.get("motion") or 0.0),
                )
            except Exception:
                pass

        js = ffprobe_json(self.ffprobe_path, path)
        fmt = js.get("format", {})
        streams = js.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not v:
            return None

        duration = float(fmt.get("duration") or v.get("duration") or 0.0)
        width = int(v.get("width") or 0)
        height = int(v.get("height") or 0)

        # For static images, ffprobe might return duration 0 or very small (0.04 for 1 frame)
        is_image = Path(path).suffix.lower() in IMAGE_EXTS
        if is_image:
            # Force a long virtual duration so the editor can treat it like a long video
            duration = 3600.0  
            # Motion check for images is always 0
            # We skip heavy compute for them
        
        r = v.get("r_frame_rate") or "0/0"
        try:
            num, den = r.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 0.0
        except Exception:
            fps = 0.0

        if is_image and fps <= 0:
            fps = 30.0

        motion = float(self._cache.get(path, {}).get("motion", 0.0))

        self._cache[path] = {
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "motion": motion,
            "motion_computed": bool(self._cache.get(path, {}).get("motion_computed", False)),
            "size": size,
            "mtime_ns": mtime_ns,
        }
        self._save_cache()

        return ClipMeta(path=path, duration=duration, width=width, height=height, fps=fps, motion=motion)

    def _estimate_motion(self, path: str, seconds: float = 1.0) -> float:
        """Cheap motion score using raw grayscale frames over a short window."""
        if Path(path).suffix.lower() in IMAGE_EXTS:
            return 0.0

        # Read ~30 frames at 30fps-equivalent (fps=15 to reduce IO)
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            path,
            "-t",
            str(seconds),
            "-vf",
            "fps=15,scale=160:-1,format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            return 0.0

        data = proc.stdout
        # Infer frame size from scale=160:-1 using probed height ratio
        meta = self._metas.get(path) or self._probe_meta(path)
        if meta.width <= 0 or meta.height <= 0:
            return 0.0

        scaled_w = 160
        scaled_h = max(2, int(round(meta.height * (scaled_w / meta.width))))
        frame_bytes = scaled_w * scaled_h
        if frame_bytes <= 0:
            return 0.0

        n_frames = len(data) // frame_bytes
        if n_frames < 2:
            return 0.0

        arr = np.frombuffer(data[: n_frames * frame_bytes], dtype=np.uint8)
        frames = arr.reshape((n_frames, scaled_h, scaled_w)).astype(np.float32)
        diffs = np.abs(frames[1:] - frames[:-1]).mean(axis=(1, 2))
        score = float(np.clip(diffs.mean() / 255.0, 0.0, 1.0))
        return score

    def load_theme(self, themes: list[str]) -> list[ClipMeta]:
        files: list[str] = []
        for t in themes:
            files.extend(list(self._iter_theme_files(t)))

        # Deduplicate
        files = list(dict.fromkeys(files))
        metas: list[ClipMeta] = []

        print(f"🔍 Checking/Indexing {len(files)} clips for themes {themes}...")
        
        changed = False
        for i, path in enumerate(files):
            if i % 10 == 0 and i > 0:
                print(f"  ... {i}/{len(files)} clips verified")

            if path not in self._metas:
                meta = self._probe_meta(path)
                if meta:
                    self._metas[path] = meta
                else:
                    continue

            meta = self._metas[path]

            # Use cached motion if available, otherwise compute it
            if meta.motion == 0.0 and self._cache.get(path, {}).get("motion_computed") is not True:
                print(f"  🎬 Computing motion for: {Path(path).name}...", end=" ", flush=True)
                motion = self._estimate_motion(path)
                print(f"score={motion:.3f}")
                meta = ClipMeta(
                    path=meta.path,
                    duration=meta.duration,
                    width=meta.width,
                    height=meta.height,
                    fps=meta.fps,
                    motion=motion
                )
                self._metas[path] = meta
                p = Path(path)
                try:
                    st = p.stat()
                    size = int(st.st_size)
                    mtime_ns = int(st.st_mtime_ns)
                except Exception:
                    size = -1
                    mtime_ns = -1

                self._cache[path] = {
                    "duration": meta.duration,
                    "width": meta.width,
                    "height": meta.height,
                    "fps": meta.fps,
                    "motion": motion,
                    "motion_computed": True,
                    "size": size,
                    "mtime_ns": mtime_ns,
                }
                changed = True

            metas.append(meta)

        if changed:
            self._save_cache()

        # Filter unusable
        metas = [m for m in metas if m.duration and m.duration > 0.5 and m.width > 0 and m.height > 0]
        return metas

    def load_files(self, files: list[str]) -> list[ClipMeta]:
        """Load metas for an explicit list of file paths (not theme-based)."""

        # Deduplicate while preserving order
        files = [str(Path(p).resolve()) for p in files]
        files = list(dict.fromkeys(files))

        metas: list[ClipMeta] = []
        changed = False

        for path in files:
            p = Path(path)
            if not p.exists() or not p.is_file() or p.suffix.lower() not in VIDEO_EXTS:
                continue

            if path not in self._metas:
                meta = self._probe_meta(path)
                self._metas[path] = meta

            meta = self._metas[path]

            if meta.motion == 0.0 and self._cache.get(path, {}).get("motion_computed") is not True:
                motion = self._estimate_motion(path)
                meta.motion = motion
                self._metas[path] = meta
                try:
                    st = p.stat()
                    size = int(st.st_size)
                    mtime_ns = int(st.st_mtime_ns)
                except Exception:
                    size = -1
                    mtime_ns = -1

                self._cache[path] = {
                    "duration": meta.duration,
                    "width": meta.width,
                    "height": meta.height,
                    "fps": meta.fps,
                    "motion": motion,
                    "motion_computed": True,
                    "size": size,
                    "mtime_ns": mtime_ns,
                }
                changed = True

            metas.append(meta)

        if changed:
            self._save_cache()

        metas = [m for m in metas if m.duration and m.duration > 0.5 and m.width > 0 and m.height > 0]
        return metas

    def choose_unique_clips(self, metas: list[ClipMeta], count: int, prefer_motion: bool) -> list[ClipMeta]:
        if len(metas) <= count:
            return metas[:]

        if prefer_motion:
            metas_sorted = sorted(metas, key=lambda m: m.motion, reverse=True)
            top = metas_sorted[: max(count * 2, min(len(metas_sorted), 30))]
            return random.sample(top, count)

        return random.sample(metas, count)

    def debug_summary(self, metas: list[ClipMeta], project_root: str) -> str:
        lines = []
        for m in sorted(metas, key=lambda x: x.motion, reverse=True)[:10]:
            lines.append(f"{safe_relpath(m.path, project_root)} dur={m.duration:.2f}s motion={m.motion:.3f}")
        return "\n".join(lines)
