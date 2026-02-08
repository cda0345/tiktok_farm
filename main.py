from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from core.audio_handler import analyze_beats
from core.ai_client import OpenAIConfig, generate_caption_and_hashtags, is_openai_configured
from logic.broll_loader import BrollLibrary
from core.config import PathsConfig, RenderConfig
from logic.editor import build_edit_plan
from logic.exporter_fast import export_video_fast as export_video
from core.ffmpeg_utils import ensure_ffmpeg
from core.gpu import detect_gpu_plan
from logic.post_parser import parse_caption_file
from logic.online_pipeline import OnlineArgs, run_online_pipeline
from logic.fetch_lyrics import fetch_and_save_lyrics
from logic.lrc_parser import parse_lrc


def _seed_from(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False) % (2**31 - 1)


def _iter_posts(posts_dir: str) -> list[str]:
    base = Path(posts_dir)
    if not base.exists():
        return []
    out: list[str] = []
    for p in sorted(base.iterdir()):
        if p.is_dir() and (p / "caption.txt").exists():
            out.append(str(p.resolve()))
    return out


def _init_caption_file(*, post_dir: str, track_id: str, themes: list[str], overwrite: bool) -> None:
    p = Path(post_dir) / "caption.txt"
    if p.exists() and not overwrite:
        return

    cfg = OpenAIConfig()
    if not is_openai_configured(cfg):
        raise SystemExit(f"{cfg.api_key_env} not set")

    caption, hashtags = generate_caption_and_hashtags(
        themes=themes,
        niche="HOUSE MUSIC + LIFESTYLE / NIGHTLIFE / LUXURY",
        cfg=cfg,
    )

    p.write_text(
        "\n".join(
            [
                caption,
                hashtags,
                f"track_id={track_id}",
                f"themes={','.join(themes)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--broll-dir", default=str(Path("broll")))
    ap.add_argument("--posts-dir", default=str(Path("posts")))
    ap.add_argument("--audio-dir", default=str(Path("audio") / "tracks"))
    ap.add_argument("--tools-dir", default=str(Path("tools")))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--only", default=None, help="Process only one post folder name, e.g. post_001")
    ap.add_argument("--init-caption", action="store_true", help="Generate caption.txt via OpenAI for --only post.")
    ap.add_argument("--init-track-id", default=None, help="Used with --init-caption. Example: house_127bpm_01")
    ap.add_argument("--init-themes", default=None, help="Used with --init-caption. Example: nightlife,luxury,city")

    # Online pipeline (downloads + caption + render)
    ap.add_argument("--online", action="store_true", help="Run the online pipeline (downloads + caption + render).")
    ap.add_argument("--online-post-name", default=None, help="Optional post folder name (defaults to timestamped).")
    ap.add_argument("--online-provider", default="pexels", choices=["pexels", "local", "youtube"], help="Video provider for b-roll library.")
    ap.add_argument("--online-themes", default=None, help="Themes for local broll/ folders (comma-separated).")
    ap.add_argument("--online-track-id", default=None, help="Required for --online. Example: house_127bpm_01")
    ap.add_argument("--online-track-file", default=None, help="Optional: path to an MP3 file to copy into audio_dir.")
    ap.add_argument("--online-broll-style", default="aesthetic", help="broll_library/<style> folder name (for provider downloads).")
    ap.add_argument("--online-broll-query", default=None, help="Search query for provider (defaults to style).")
    ap.add_argument("--online-broll-min-videos", type=int, default=12, help="Minimum videos to keep in broll_library/style.")

    args = ap.parse_args()

    project_root = str(Path(args.project_root).resolve())
    broll_dir = str((Path(project_root) / args.broll_dir).resolve())
    posts_dir = str((Path(project_root) / args.posts_dir).resolve())
    audio_dir = str((Path(project_root) / args.audio_dir).resolve())
    tools_dir = str((Path(project_root) / args.tools_dir).resolve())
    
    mediahuman_dir = "/Users/caioalbanese/Music/Downloaded by MediaHuman"

    paths = PathsConfig(
        project_root=project_root,
        broll_dir=broll_dir,
        posts_dir=posts_dir,
        audio_dir=audio_dir,
        tools_dir=tools_dir,
        mediahuman_dir=mediahuman_dir,
    )

    cfg = RenderConfig()

    bins = ensure_ffmpeg(paths.tools_dir)
    gpu = detect_gpu_plan(bins.ffmpeg)

    lib = BrollLibrary(broll_dir=paths.broll_dir, ffmpeg_path=bins.ffmpeg, ffprobe_path=bins.ffprobe)

    if args.online:
        if not args.online_track_id:
            raise SystemExit("--online requires --online-track-id")

        themes = []
        if args.online_themes:
            themes = [t.strip() for t in str(args.online_themes).split(",") if t.strip()]

        post_dir = run_online_pipeline(
            paths=paths,
            cfg=cfg,
            args=OnlineArgs(
                post_name=str(args.online_post_name).strip() if args.online_post_name else None,
                themes=themes,
                track_id=str(args.online_track_id).strip(),
                track_file=str(args.online_track_file).strip() if args.online_track_file else None,
                broll_style=str(args.online_broll_style).strip() if args.online_broll_style else None,
                broll_query=str(args.online_broll_query).strip() if args.online_broll_query else None,
                broll_min_videos=int(args.online_broll_min_videos),
                provider=str(args.online_provider),
                overwrite=bool(args.overwrite),
            ),
        )
        print(f"\n[online] Completed. Post created at: {post_dir}")
        return 0

    if args.init_caption:
        if not args.only:
            raise SystemExit("--init-caption requires --only post folder")
        if not args.init_track_id or not args.init_themes:
            raise SystemExit("--init-caption requires --init-track-id and --init-themes")

        themes = [t.strip() for t in str(args.init_themes).split(",") if t.strip()]
        if not themes:
            raise SystemExit("--init-themes cannot be empty")

        post_dir = str((Path(paths.posts_dir) / args.only).resolve())
        if not Path(post_dir).exists():
            raise SystemExit(f"Post folder does not exist: {post_dir}")

        _init_caption_file(
            post_dir=post_dir,
            track_id=str(args.init_track_id).strip(),
            themes=themes,
            overwrite=bool(args.overwrite),
        )
        return 0

    post_dirs = _iter_posts(paths.posts_dir)
    if args.only:
        only_list = [s.strip() for s in str(args.only).split(",") if s.strip()]
        post_dirs = [p for p in post_dirs if Path(p).name in only_list]

    if not post_dirs:
        raise SystemExit(f"No posts found in {paths.posts_dir} (missing caption.txt?)")

    for post_dir in post_dirs:
        print(f"\n=== Processing post: {Path(post_dir).name} ===")
        # If caption exists, parse normally.
        # If missing, auto-caption needs themes/track_id; simplest path is: user creates caption.txt.
        spec = parse_caption_file(post_dir)
        
        # Auto-fetch lyrics
        fetch_and_save_lyrics(post_dir, spec.track_id)
        
        track_path = Path(paths.audio_dir) / f"{spec.track_id}.mp3"

        # Check MediaHuman folder if not in audio/tracks
        if not track_path.exists():
            mh_track = Path(paths.mediahuman_dir) / f"{spec.track_id}.mp3"
            if mh_track.exists():
                print(f"Copying track from MediaHuman: {mh_track}")
                track_path.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(mh_track, track_path)

        track_path_str = str(track_path.resolve())

        if not Path(track_path_str).exists():
            available = sorted([p.name for p in Path(paths.audio_dir).glob("*.mp3")])
            msg = [
                f"Missing audio track: {track_path_str}",
                f"Put the MP3 here: {paths.audio_dir}",
                "Or change track_id in caption.txt to match an existing MP3 filename (without .mp3).",
            ]
            if available:
                msg.append("Available tracks:")
                msg.extend([f"- {n}" for n in available[:50]])
            raise SystemExit("\n".join(msg))

        print(f"Audio: {Path(track_path).name}")
        beats = analyze_beats(track_path_str)
        print(f"Beat analysis: bpm={beats.bpm:.1f} start_offset={beats.start_offset:.2f}s")

        print(f"Loading b-roll themes: {', '.join(spec.themes)}")
        metas = lib.load_theme(spec.themes)
        print(f"B-roll clips found: {len(metas)}")
        if len(metas) < 2:
            theme_dirs = [str((Path(paths.broll_dir) / t).resolve()) for t in spec.themes]
            msg = [
                f"Not enough B-roll clips for themes {spec.themes} (found {len(metas)})",
                "Add videos (.mp4/.mov/.mkv/.webm/.m4v) into these folders:",
            ]
            msg.extend([f"- {d}" for d in theme_dirs])
            raise SystemExit("\n".join(msg))

        if len(metas) < 6:
            print(f"Warning: small clip library ({len(metas)}). The editor will reuse clips.")

        out_dir = Path(spec.post_dir) / "output"
        out_dir.mkdir(parents=True, exist_ok=True)

        for v in (1, 2, 3):
            out_path = out_dir / f"v{v}.mp4"
            if out_path.exists() and not args.overwrite:
                continue

            print(f"Rendering v{v} -> {out_path.name}")

            seed = _seed_from(Path(spec.post_dir).name, spec.track_id, ",".join(spec.themes), f"v{v}")
            print(f"  Building edit plan (seed={seed})...")
            plan = build_edit_plan(metas=metas, beat=beats, cfg=cfg, seed=seed)
            print(f"  Plan ready: {len(plan.segments)} segments, {plan.duration:.2f}s total")

            # Determine overlay text: strict "City & HouseMusic" format as requested
            cities_map = {
                "ibiza": "Ibiza",
                "roma": "Roma",
                "paris": "Paris",
                "london": "London",
                "berlin": "Berlin",
                "amsterdam": "Amsterdam"
            }
            
            overlay_text = "House Music" # Default fallback
            for t in spec.themes:
                t_low = t.lower().strip()
                if t_low in cities_map:
                    overlay_text = f"{cities_map[t_low]} & HouseMusic"
                    break
            
            # If not found in themes, try to infer from post directory name
            if overlay_text == "House Music":
                folder_name = Path(spec.post_dir).name.lower()
                for city_key, city_name in cities_map.items():
                    if city_key in folder_name:
                        overlay_text = f"{city_name} & HouseMusic"
                        break

            # Handle Lyrics
            lyrics_events = []
            lyrics_path = Path(post_dir) / "lyrics.lrc"
            if lyrics_path.exists():
                raw_events = parse_lrc(lyrics_path)
                for l_start, l_end, l_text in raw_events:
                    # Shift by lyrics_offset (e.g. if lyrics_offset is 84.51, 
                    # we want the lyric that was at 84.51 in the song to appear at 0.0 in the video)
                    # Shift = LyricTime - Offset
                    shifted_start = l_start - spec.lyrics_offset
                    shifted_end = l_end - spec.lyrics_offset
                    # Add if it falls within a reasonable window for the video (0-~15s)
                    if shifted_end > 0 and shifted_start < 20.0:
                        lyrics_events.append((shifted_start, shifted_end, l_text))

            print(f"🎬 Starting Engine: FAST 2-PASS (Overlay: {overlay_text}, Lyrics: {len(lyrics_events)})")
            export_video(
                ffmpeg_path=bins.ffmpeg,
                gpu=gpu,
                plan=plan,
                audio_path=track_path_str,
                audio_start_offset=beats.start_offset + spec.lyrics_offset,
                out_path=str(out_path),
                cfg=cfg,
                overlay_text=overlay_text,
                lyrics=lyrics_events,
            )

            print(f"Done v{v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
