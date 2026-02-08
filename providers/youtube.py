from __future__ import annotations

import os
import random
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from core.ffmpeg_utils import ensure_ffmpeg
from providers.base import DownloadedAsset
from logic.broll_categories import get_broll_category

# Blacklist: IDs de vídeos indesejados (tutoriais, duplicatas, etc)
BLACKLIST_VIDEO_IDS = {
    "b2JvzT2sYhg",  # Tutorial: mixing techniques
    "fLdnb24DgH4",  # Tutorial: DJ mixing guide
    "tr4Uk7WaBKo",  # Duplicate of V9H0F0pfLNM
    "gCUEXpI9rmk",  # Unwanted content
    "h3t3YnVgY9k",  # Unwanted content
    "rAbe9QJD7LA",  # Unwanted content
    "WiXHj2nYy1o",  # Unwanted content
    "j4EJKcnGSHk",  # Unwanted content
    "UCT5Ggpdar0",  # Unwanted content
    # Batch 2: Jazz lounge / wrong vibes
    "F1JaL6gFrYo",  # Jazz lounge (not nightclub)
    "-iAy41rMnWw",  # Wrong atmosphere
    "h0VQEEj--_U",  # Unwanted
    "yi9xG76nbUo",  # Unwanted
    "JQ4EqAlkgC8",  # Unwanted
    "liu-WYs6kG4",  # Unwanted
    "SxdWManXTnw",  # Unwanted
    "BwGiqIrsTuE",  # Unwanted
    "cCFMN0r1ZHY",  # Unwanted
    "QlQRGaQJ23M",  # Unwanted
    "uhdzeRNW8Ds",  # Unwanted
    "6V3fr4xcC0Q",  # Unwanted
    "WS_Qt4oFA6o",  # Unwanted
    "0p9o7sjjVJY",  # Jazz bar (not club)
    "3v-IINFNs-8",  # Unwanted
    "D7MpuetgTBo",  # Unwanted
    "V0_OjSnp3AM",  # Unwanted (duplicate entry)
    "HA_uRtCDjKs",  # Disco ball animation
    "6DFHMoYbmG0",  # Wrong vibe
    "s02qli6kOUU",  # Unwanted
    "GuoFW2yAD7g",  # Unwanted
    "UCDt9oucaOE",  # Unwanted
    "yTi8nKvImv4",  # Unwanted
    "6SQG3XdhR6w",  # Unwanted
    "_WzrK6CIZrY",  # Unwanted
    # Batch 3: Additional blacklist
    "gQ8CjhJ0J-c",  # Unwanted
    "bEkQHiaTZ90",  # Unwanted
    "M7qFdmm17Ak",  # Unwanted
    "NTJANVBV-bc",  # Unwanted
    "2_mxfkvmgqg",  # Unwanted
    "-IlEjUI2VNA",  # Unwanted
    # Batch 4: Bad quality / unwanted footage
    "GIPHwnokWiw",  # Bad DJ footage
    "gZ9k5R5hkfI",  # Bad DJ footage
    "xIoL-bmn9HM",  # Bad nightlife footage
    "aqJFMjfOXr0",  # Bad abstract aesthetic footage
    "4ysDVLfAcvU",  # Bad abstract aesthetic footage
    "9BizUCFvWXw",  # Bad nightlife crowd footage
    "BcSXWOhKa4w",  # Bad nightlife crowd footage
    "TuHfMs7lD88",  # Bad nightlife crowd footage
    "JR3TlVpNvH8",  # Bad nightlife crowd footage
    "Kh1v7LLk0Qw",  # User blacklisted
    "FEE3BkoAg0Y",  # User blacklisted
}


def _normalize_text(s: str) -> str:
    return " ".join((s or "").lower().replace("-", " ").split())


def _get_ffmpeg_path() -> str:
    """Get FFmpeg binary path for yt-dlp."""
    from pathlib import Path
    bins = ensure_ffmpeg(Path.cwd() / "tools")
    # Return the directory containing ffmpeg.exe
    return str(Path(bins.ffmpeg).parent)


def _common_ydl_opts() -> dict:
    """Common yt-dlp options for resilience."""
    return {
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "noprogress": False,
        "quiet": False,
        "no_warnings": False,
        "ffmpeg_location": _get_ffmpeg_path(),
    }


@dataclass(frozen=True)
class YouTubeVideoProvider:
    """Downloads video clips from YouTube for b-roll library."""

    def ensure_videos(self, *, query: str, dest_dir: str, min_count: int) -> list[DownloadedAsset]:
        # Mapeia query para macro-categoria
        category = get_broll_category(query)
        
        # Usa pasta da categoria ao invés da query literal
        base_dir = Path(dest_dir).parent / category
        dest = base_dir
        dest.mkdir(parents=True, exist_ok=True)

        print(f"[youtube] Query: {query!r} -> Category: {category}")

        # Reuse existing
        existing = sorted(dest.glob("*.mp4"))
        assets: list[DownloadedAsset] = [
            DownloadedAsset(path=str(p.resolve()), source="youtube:cache") for p in existing
        ]
        if len(assets) >= min_count:
            print(f"[youtube] Using {len(assets)} cached videos from category {category}")
            return assets[:min_count]

        need = min_count - len(assets)
        print(f"[youtube] Searching videos for: {query!r} (need {need} more)")

        match_filter = yt_dlp.utils.match_filter_func("!is_live & duration>=15 & duration<=3600")

        ydl_opts = {
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "default_search": "ytsearch20:",
            "outtmpl": str(dest / "yt_%(id)s.%(ext)s"),
            "noplaylist": True,
            "merge_output_format": "mp4",
            "match_filter": match_filter,
            "ignoreerrors": True,  # Continue on download errors
            **_common_ydl_opts(),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            entries = info.get("entries") if isinstance(info, dict) else None
            entries = entries or []

            candidates = [e for e in entries if isinstance(e, dict)]

            # Filter out bad quality (static, loops, radio streams, tutorials)
            def _is_bad_quality(e: dict) -> bool:
                title = _normalize_text(e.get("title") or "")
                bad_keywords = [
                    "radio",
                    "stream",
                    "live stream",
                    "24/7",
                    "non stop",
                    "still image",
                    "loop",
                    "hours",
                    "relaxing",
                    "study",
                    "chill",
                    "tutorial",
                    "how to",
                    "guide",
                    "lesson",
                    "course",
                    "learn",
                    "tips",
                    "tricks",
                ]
                return any(k in title for k in bad_keywords)

            def _is_blacklisted(e: dict) -> bool:
                vid = e.get("id")
                return vid in BLACKLIST_VIDEO_IDS if vid else False

            candidates = [e for e in candidates if not _is_bad_quality(e) and not _is_blacklisted(e)]

            for e in candidates:
                if need <= 0:
                    break

                url = e.get("webpage_url") or e.get("url")
                if not url:
                    continue
                if not url.startswith("http"):
                    url = f"https://www.youtube.com/watch?v={url}"

                vid = e.get("id")
                
                # Skip blacklisted videos
                if vid in BLACKLIST_VIDEO_IDS:
                    continue
                    
                out = dest / f"yt_{vid}.mp4"
                if out.exists() and out.stat().st_size > 200 * 1024:
                    assets.append(DownloadedAsset(path=str(out.resolve()), source=f"youtube:{vid}"))
                    need -= 1
                    continue

                # Download segment (60s from a random point after first minute)
                duration = e.get("duration") or 600
                segment_duration = 60
                start_min = 60
                max_possible_start = max(start_min, int(duration) - (segment_duration + 10))
                max_start = min(max_possible_start, 900)
                start_time = random.randint(start_min, max_start) if max_start > start_min else start_min
                end_time = start_time + segment_duration

                current_opts = ydl_opts.copy()
                current_opts["download_sections"] = [
                    {"start_time": start_time, "end_time": end_time, "title": "section"}
                ]

                try:
                    print(f"[youtube] Downloading {vid} ({start_time}s-{end_time}s)...")
                    with yt_dlp.YoutubeDL(current_opts) as ydl_run:
                        ydl_run.extract_info(url, download=True)

                    if out.exists() and out.stat().st_size > 100 * 1024:
                        assets.append(DownloadedAsset(path=str(out.resolve()), source=f"youtube:{vid}"))
                        need -= 1
                except Exception as ex:
                    print(f"[youtube] Failed to download {vid}: {ex}")
                    continue

        if len(assets) < min_count:
            raise RuntimeError(
                f"YouTube provider could only get {len(assets)} videos (need {min_count})."
            )

        return assets[:min_count]


@dataclass(frozen=True)
class YouTubeAudioProvider:
    """Downloads audio tracks from YouTube."""

    def ensure_audio(self, *, track_id: str, dest_dir: str, artist_name: str | None = None) -> DownloadedAsset:
        dest = Path(dest_dir) / f"{track_id}.mp3"
        if dest.exists():
            return DownloadedAsset(path=str(dest.resolve()), source="youtube:cache")

        query = artist_name or track_id
        print(f"[youtube] Searching audio for: {query!r}")

        match_filter = yt_dlp.utils.match_filter_func("!is_live & duration>=90 & duration<=900")

        ydl_opts = {
            "format": "bestaudio/best",
            "default_search": "ytsearch10:",
            "outtmpl": str(dest).replace(".mp3", ".%(ext)s"),
            "noplaylist": True,
            "match_filter": match_filter,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            **_common_ydl_opts(),
        }

        def _audio_candidate_ok(entry: dict) -> bool:
            if not isinstance(entry, dict):
                return False
            title = _normalize_text(entry.get("title") or "")
            bad = [
                "dj set",
                "live set",
                "full set",
                "podcast",
                "essential mix",
                "boiler room",
                "cercle",
                "tomorrowland",
                "ultra",
                "coachella",
                "full album",
                "compilation",
            ]
            return not any(b in title for b in bad)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            entries = info.get("entries") if isinstance(info, dict) else None
            entries = entries or []

            candidates = [e for e in entries if _audio_candidate_ok(e)]
            if not candidates:
                raise RuntimeError(f"No suitable audio found for {query}")

            # Sort by popularity
            def _popularity_key(e: dict):
                vc = e.get("view_count") or 0
                try:
                    return int(vc)
                except Exception:
                    return 0

            candidates.sort(key=_popularity_key, reverse=True)
            best = candidates[0]

            url = best.get("webpage_url") or best.get("url")
            if not url:
                raise RuntimeError(f"No URL found for audio {query}")
            if not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={url}"

            print(f"[youtube] Downloading audio: {best.get('title', 'Unknown')}")
            ydl.extract_info(url, download=True)

        if not dest.exists():
            raise RuntimeError(f"Failed to download audio for {query}")

        return DownloadedAsset(path=str(dest.resolve()), source=f"youtube:{best.get('id')}")
