from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.ai_client import OpenAIConfig, generate_caption_and_hashtags, generate_final_caption, is_openai_configured
from core.audio_handler import analyze_beats
from logic.broll_loader import BrollLibrary
from core.config import PathsConfig, RenderConfig
from logic.editor import build_edit_plan
from logic.exporter_fast import export_video_fast
from core.ffmpeg_utils import ensure_ffmpeg
from core.gpu import detect_gpu_plan
from providers.local import LocalAudioProvider
from providers.pexels import PexelsVideoProvider
from providers.youtube import YouTubeAudioProvider
from logic.fetch_lyrics import fetch_and_save_lyrics


def _slug(s: str) -> str:
    s = "".join([c if c.isalnum() else "_" for c in (s or "").strip().lower()])
    s = "_".join([p for p in s.split("_") if p])
    return s[:60] or "post"


def _seed_from(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False) % (2**31 - 1)


@dataclass(frozen=True)
class OnlineArgs:
    post_name: str | None
    themes: list[str]
    track_id: str
    track_file: str | None

    # b-roll library provider
    broll_style: str | None
    broll_query: str | None
    broll_min_videos: int
    provider: str

    overwrite: bool


def run_online_pipeline(*, paths: PathsConfig, cfg: RenderConfig, args: OnlineArgs) -> str:
    """Creates a new post folder, ensures assets exist, generates caption, renders video.

    Returns the created post folder path.

    Notes:
    - This pipeline supports multiple providers (pexels, youtube, local).
    - For YouTube provider, both video and audio can be downloaded automatically.
    - For pexels/local providers, audio is expected to be local or copied from track_file.
    """

    bins = ensure_ffmpeg(paths.tools_dir)
    gpu = detect_gpu_plan(bins.ffmpeg)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = args.post_name or f"post_online_{ts}_{_slug(args.track_id)}"
    post_dir = Path(paths.posts_dir) / base_name
    post_dir.mkdir(parents=True, exist_ok=True)

    effective_themes = list(args.themes or [])
    if not effective_themes and args.broll_style:
        effective_themes = [args.broll_style]
    if not effective_themes:
        raise ValueError("Online pipeline requires at least one theme (themes or broll_style).")

    print(f"[online] Post folder: {post_dir}")

    # --- Audio ---
    if args.track_file:
        audio_provider = LocalAudioProvider(track_file=args.track_file)
    elif args.provider == "youtube":
        # Check MediaHuman first even for youtube provider if we want it as priority
        mh_dir = Path(paths.mediahuman_dir)
        mh_track = mh_dir / f"{args.track_id}.mp3"
        if mh_track.exists():
            print(f"[online] Found track in MediaHuman folder: {mh_track}")
            audio_provider = LocalAudioProvider(track_file=str(mh_track))
        else:
            # Use YouTube for audio when no local file found
            audio_provider = YouTubeAudioProvider()
    else:
        # Default to local (checks MediaHuman folder first)
        mh_dir = Path(paths.mediahuman_dir)
        mh_track = mh_dir / f"{args.track_id}.mp3"
        if mh_track.exists():
            print(f"[online] Found track in MediaHuman folder: {mh_track}")
            audio_provider = LocalAudioProvider(track_file=str(mh_track))
        else:
            audio_provider = LocalAudioProvider(track_file=None)

    audio_asset = audio_provider.ensure_audio(track_id=args.track_id, dest_dir=paths.audio_dir)
    print(f"[online] Audio: {audio_asset.path}")
    beats = analyze_beats(audio_asset.path)
    print(f"[online] Beat analysis: bpm={beats.bpm:.1f} start_offset={beats.start_offset:.2f}s")

    # --- Videos (b-roll library) ---
    metas = []
    if args.broll_style:
        lib_root = Path(paths.project_root) / "broll_library"
        style_dir = lib_root / args.broll_style

        print(
            f"[online] Ensuring b-roll library style={args.broll_style!r} provider={args.provider} min={args.broll_min_videos}"
        )

        query = args.broll_query or args.broll_style
        if args.provider == "pexels":
            video_provider = PexelsVideoProvider()
        elif args.provider == "youtube":
            from providers.youtube import YouTubeVideoProvider

            video_provider = YouTubeVideoProvider()
        elif args.provider == "local":
            from providers.local import LocalVideoProvider

            video_provider = LocalVideoProvider()
        else:
            raise ValueError("provider must be one of: local, pexels, youtube")

        video_assets = video_provider.ensure_videos(query=query, dest_dir=str(style_dir), min_count=int(args.broll_min_videos))
        video_paths = [a.path for a in video_assets]

        print(f"[online] B-roll clips available: {len(video_paths)}")

        # Use BrollLibrary to probe + motion-score arbitrary files
        lib = BrollLibrary(
            broll_dir=str(lib_root),
            ffmpeg_path=bins.ffmpeg,
            ffprobe_path=bins.ffprobe,
            cache_path=str(lib_root / "_cache.json"),
        )
        metas.extend(lib.load_files(video_paths))

    # --- Local theme folders (optional) ---
    if args.themes:
        theme_lib = BrollLibrary(
            broll_dir=paths.broll_dir,
            ffmpeg_path=bins.ffmpeg,
            ffprobe_path=bins.ffprobe,
        )
        metas.extend(theme_lib.load_theme(args.themes))

    # Deduplicate by path
    metas_by_path = {m.path: m for m in metas}
    metas = list(metas_by_path.values())

    if len(metas) < 6:
        if len(metas) < 2:
            raise RuntimeError(
                f"Not enough video clips for rendering (found {len(metas)}, need >= 2). "
                "Add more local b-roll or increase --online-broll-min-videos with a provider."
            )
        print(f"[online] Warning: small clip library ({len(metas)}). The editor will reuse clips.")

    print(f"[online] Total unique clips for edit plan: {len(metas)}")

    out_dir = post_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Captions ---
    oai_cfg = OpenAIConfig()
    if not is_openai_configured(oai_cfg):
        print(f"[online] Warning: {oai_cfg.api_key_env} not set; using placeholder captions.")
        caption_line1 = "Midnight city flow"
        hashtags_line2 = "#housemusic #nightlife #cityvibes #fyp"
        caption_final = f"{caption_line1}\n{hashtags_line2}"
    else:
        print("[online] Generating captions via OpenAI...")

        # Spec (engine-friendly)
        caption_line1, hashtags_line2 = generate_caption_and_hashtags(
            themes=effective_themes,
            track_id=args.track_id,
            niche="HOUSE MUSIC + LIFESTYLE / NIGHTLIFE / LUXURY",
            cfg=oai_cfg,
        )

        # Final (human-facing)
        caption_final = generate_final_caption(
            themes=effective_themes,
            niche="HOUSE MUSIC + LIFESTYLE / NIGHTLIFE / LUXURY",
            track_id=args.track_id,
            cfg=oai_cfg,
        )

    (post_dir / "caption_spec.txt").write_text(
        "\n".join(
            [
                caption_line1,
                hashtags_line2,
                f"track_id={args.track_id}",
                f"themes={','.join(effective_themes)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (post_dir / "caption.txt").write_text(caption_final.strip() + "\n", encoding="utf-8")

    # --- Fetch Lyrics ---
    print(f"[online] Fetching lyrics for {args.track_id}...")
    fetch_and_save_lyrics(post_dir, args.track_id)

    # Track all videos used across all variants
    all_used_videos = []

    # --- Render 3 variants ---
    for v in (1, 2, 3):
        out_path = out_dir / f"v{v}.mp4"
        if out_path.exists() and not args.overwrite:
            continue

        print(f"[online] Rendering v{v} -> {out_path}")

        # Randomize duration between 8-10s per variant
        import random
        random.seed(_seed_from(post_dir.name, args.track_id, ",".join(args.themes), f"v{v}_duration"))
        variant_duration = random.uniform(8.0, 10.0)
        variant_cfg = RenderConfig(max_duration_s=variant_duration)
        
        seed = _seed_from(post_dir.name, args.track_id, ",".join(args.themes), f"v{v}")
        plan = build_edit_plan(metas=metas, beat=beats, cfg=variant_cfg, seed=seed)

        # Track videos used in this variant
        if plan.used_videos:
            all_used_videos.extend(plan.used_videos)

        export_video_fast(
            ffmpeg_path=bins.ffmpeg,
            gpu=gpu,
            plan=plan,
            audio_path=audio_asset.path,
            audio_start_offset=beats.start_offset,
            out_path=str(out_path),
            cfg=variant_cfg,
            max_workers=4,  # Parallel segment rendering
        )

        print(f"[online] Done v{v}")

    # Save JSON with all videos used in this post
    unique_videos = list(dict.fromkeys(all_used_videos))  # Remove duplicates while preserving order
    videos_json = {
        "post_name": base_name,
        "track_id": args.track_id,
        "themes": effective_themes,
        "total_unique_videos": len(unique_videos),
        "videos": [
            {
                "path": video_path,
                "filename": Path(video_path).name,
                "video_id": Path(video_path).stem  # e.g., "yt_VIDEO_ID"
            }
            for video_path in unique_videos
        ],
        "generated_at": datetime.now().isoformat()
    }
    
    videos_json_path = post_dir / "videos_used.json"
    with open(videos_json_path, "w", encoding="utf-8") as f:
        json.dump(videos_json, f, indent=2, ensure_ascii=False)
    
    print(f"[online] Saved videos manifest: {videos_json_path}")

    return str(post_dir.resolve())
