from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from providers.base import DownloadedAsset


_PEXELS_VIDEOS_API = "https://api.pexels.com/videos/search"
_PEXELS_IMAGES_API = "https://api.pexels.com/v1/search"


@dataclass(frozen=True)
class PexelsConfig:
    api_key_env: str = "PEXELS_API_KEY"


def _get_key(cfg: PexelsConfig) -> str:
    key = os.getenv(cfg.api_key_env, "").strip()
    if not key:
        raise RuntimeError(
            f"Missing {cfg.api_key_env}. Set it in your environment to use the Pexels provider."
        )
    return key


def _choose_video_file(video: dict) -> str | None:
    """Pick a reasonable MP4 download URL from Pexels response."""
    files = video.get("video_files") or []
    if not isinstance(files, list) or not files:
        return None

    # Prefer vertical-ish and ~1080p, else best available
    def score(f: dict) -> tuple[int, int]:
        w = int(f.get("width") or 0)
        h = int(f.get("height") or 0)
        # Vertical preference: h>w gives a boost
        vertical = 1 if h > w else 0
        # Closer to 1080 width is better, penalize tiny
        width_score = -abs(w - 1080)
        return (vertical, width_score)

    files_sorted = sorted([f for f in files if isinstance(f, dict)], key=score, reverse=True)
    for f in files_sorted:
        link = f.get("link")
        if isinstance(link, str) and link.startswith("http"):
            return link
    return None


@dataclass(frozen=True)
class PexelsVideoProvider:
    cfg: PexelsConfig = PexelsConfig()
    per_page: int = 15

    def ensure_videos(self, *, query: str, dest_dir: str, min_count: int) -> list[DownloadedAsset]:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)

        # Reuse existing downloaded MP4s first
        existing = sorted(dest.glob("*.mp4"))
        assets: list[DownloadedAsset] = [DownloadedAsset(path=str(p.resolve()), source="pexels:cache") for p in existing]
        if len(assets) >= min_count:
            return assets[:min_count]

        key = _get_key(self.cfg)

        need = min_count - len(assets)
        page = 1
        safety = 0

        print(f"[pexels] Searching videos for: {query!r}")

        while need > 0 and safety < 10:
            safety += 1
            r = requests.get(
                _PEXELS_VIDEOS_API,
                headers={"Authorization": key},
                params={"query": query, "per_page": int(self.per_page), "page": int(page)},
                timeout=60,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"Pexels API error: {r.status_code} {r.text}")

            data = r.json() if isinstance(r.json, object) else {}
            videos = data.get("videos") or []
            if not videos:
                break

            for v in videos:
                if need <= 0:
                    break
                if not isinstance(v, dict):
                    continue

                vid = v.get("id")
                link = _choose_video_file(v)
                if not vid or not link:
                    continue

                out = dest / f"pexels_{vid}.mp4"
                if out.exists():
                    assets.append(DownloadedAsset(path=str(out.resolve()), source="pexels:cache"))
                    need = min_count - len(assets)
                    continue

                print(f"[pexels] Downloading {out.name}...")
                with requests.get(link, stream=True, timeout=120) as vr:
                    vr.raise_for_status()
                    total = int(vr.headers.get("Content-Length") or 0)
                    done = 0
                    last = 0.0

                    with open(out, "wb") as f:
                        for chunk in vr.iter_content(chunk_size=1024 * 1024):
                            if not chunk:
                                continue
                            f.write(chunk)
                            done += len(chunk)

                            now = time.time()
                            if now - last >= 0.6:
                                last = now
                                if total > 0:
                                    pct = (done / total) * 100.0
                                    sys.stdout.write(
                                        f"  {done/1024/1024:.1f}MB / {total/1024/1024:.1f}MB ({pct:.0f}%)\n"
                                    )
                                else:
                                    sys.stdout.write(f"  {done/1024/1024:.1f}MB downloaded\n")
                                sys.stdout.flush()

                # Basic sanity check
                if out.exists() and out.stat().st_size > 200 * 1024:
                    assets.append(DownloadedAsset(path=str(out.resolve()), source=f"pexels:{vid}"))
                    need = min_count - len(assets)

            page += 1

        if len(assets) < min_count:
            raise RuntimeError(f"Pexels provider could only get {len(assets)} videos (need {min_count}).")

        return assets[:min_count]


@dataclass(frozen=True)
class PexelsImageProvider:
    cfg: PexelsConfig = PexelsConfig()
    per_page: int = 15

    def ensure_images(self, *, query: str, dest_dir: str, min_count: int) -> list[DownloadedAsset]:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)

        # Reuse existing downloaded images first
        image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        existing = [p for p in dest.glob("*") if p.suffix.lower() in image_exts]
        assets: list[DownloadedAsset] = [DownloadedAsset(path=str(p.resolve()), source="pexels:cache") for p in existing]
        if len(assets) >= min_count:
            return assets[:min_count]

        key = _get_key(self.cfg)
        need = min_count - len(assets)
        page = 1
        safety = 0

        print(f"[pexels] Searching photos for: {query!r}")

        while need > 0 and safety < 10:
            safety += 1
            r = requests.get(
                _PEXELS_IMAGES_API,
                headers={"Authorization": key},
                params={"query": query, "per_page": int(self.per_page), "page": int(page)},
                timeout=60,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"Pexels API error: {r.status_code} {r.text}")

            data = r.json()
            photos = data.get("photos") or []
            if not photos:
                break

            for p in photos:
                pid = p.get("id")
                # Prefer portrait or original if available
                src = p.get("src") or {}
                link = src.get("portrait") or src.get("large2x") or src.get("original")
                
                if not pid or not link:
                    continue

                # Get extension from link or default to .jpg
                ext = ".jpg"
                if ".png" in link.lower(): ext = ".png"
                elif ".webp" in link.lower(): ext = ".webp"
                
                out = dest / f"pexels_photo_{pid}{ext}"
                if out.exists():
                    # If it exists, but we haven't added it to assets yet in this run
                    already_in_assets = any(a.path == str(out.resolve()) for a in assets)
                    if not already_in_assets:
                        assets.append(DownloadedAsset(path=str(out.resolve()), source="pexels:cache"))
                        need = min_count - len(assets)
                    continue

                if need <= 0:
                    break

                print(f"[pexels] Downloading {out.name}...")
                try:
                    with requests.get(link, stream=True, timeout=60) as pr:
                        pr.raise_for_status()
                        with open(out, "wb") as f:
                            for chunk in pr.iter_content(chunk_size=1024 * 1024):
                                if chunk:
                                    f.write(chunk)
                except Exception as e:
                    print(f"  Failed to download {link}: {e}")
                    continue

                if out.exists() and out.stat().st_size > 50 * 1024:
                    assets.append(DownloadedAsset(path=str(out.resolve()), source=f"pexels:{pid}"))
                    need = min_count - len(assets)

            page += 1

        return assets[:min_count]
