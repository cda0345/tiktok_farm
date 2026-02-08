import argparse
import sys
from pathlib import Path

from core.audio_handler import analyze_beats
from logic.broll_loader import BrollLibrary
from core.config import PathsConfig, RenderConfig
from logic.editor import build_edit_plan
from logic.exporter_fast import export_video_fast
from core.ffmpeg_utils import ensure_ffmpeg
from core.gpu import detect_gpu_plan
from logic.post_parser import parse_caption_file
from logic.lrc_parser import parse_lrc, find_lyrics_segment

def main():
    ap = argparse.ArgumentParser(description="Generate TikTok Lyrics video (10-15s synchronized)")
    ap.add_argument("--post", required=True, help="Folder name in posts/, e.g. post_304_ibiza_stussy")
    ap.add_argument("--start", type=float, default=None, help="Start time in seconds for the lyrics segment")
    ap.add_argument("--duration", type=float, default=15.0, help="Max duration of the clip (default 15s)")
    ap.add_argument("--overwrite", action="store_true")
    
    args = ap.parse_args()
    
    project_root = Path(__file__).resolve().parent.parent
    paths = PathsConfig(
        project_root=str(project_root),
        broll_dir="broll_library",
        posts_dir="posts",
        audio_dir="audio/tracks",
        tools_dir="tools"
    ).with_resolved_paths()
    
    post_dir = Path(paths.posts_dir) / args.post
    if not post_dir.exists():
        print(f"Post directory not found: {post_dir}")
        return

    # 1. Load Specs
    spec = parse_caption_file(str(post_dir))
    track_path = Path(paths.audio_dir) / f"{spec.track_id}.mp3"
    
    # Check MediaHuman folder if not in audio/tracks
    if not track_path.exists():
        mh_track = Path(paths.mediahuman_dir) / f"{spec.track_id}.mp3"
        if mh_track.exists():
            print(f"Copying track from MediaHuman: {mh_track}")
            track_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(mh_track, track_path)

    lrc_path = post_dir / "lyrics.lrc"
    
    if not track_path.exists():
        print(f"Audio track not found: {track_path}")
        return
    if not lrc_path.exists():
        print(f"LRC file not found: {lrc_path}. Run fetch_lyrics.py first.")
        return

    # 2. Parse LRC and find segment
    all_lyrics_raw = parse_lrc(lrc_path)
    if not all_lyrics_raw:
        print("LRC file is empty or invalid format.")
        return
    
    # Apply offset from spec (helps with Extended Mix vs Radio Edit)
    if spec.lyrics_offset != 0:
        print(f"Applying lyrics offset: {spec.lyrics_offset:+.2f}s")
    
    all_lyrics = [(s + spec.lyrics_offset, e + spec.lyrics_offset, t) for s, e, t in all_lyrics_raw]
        
    audio_start, segment_lyrics_pre = find_lyrics_segment(all_lyrics, target_duration=args.duration, start_offset=args.start)

    # 3. Setup Tools & Library
    bins = ensure_ffmpeg(paths.tools_dir)
    gpu = detect_gpu_plan(bins.ffmpeg)
    
    # Range of 10-15s for Lyrics mode as requested
    cfg = RenderConfig(
        min_duration_s=10.0 if args.duration >= 10.0 else args.duration,
        max_duration_s=args.duration
    )
    
    # Analyze beats
    beats = analyze_beats(str(track_path))
    
    # If user provided a start time, use it EXACTLY to preserve lyric sync.
    # Otherwise, find a segment and snap it.
    if args.start is not None:
        audio_start = args.start
        print(f"Using exact user-provided start time: {audio_start:.2f}s")
    else:
        # Snap audio_start to nearest beat to maintain sync for automatic detection
        quarter_note = 60.0 / beats.bpm
        beats_since_start = (audio_start - beats.start_offset) / quarter_note
        audio_start = beats.start_offset + round(beats_since_start) * quarter_note
        print(f"Automatically selected sync-point (beat-snapped): {audio_start:.2f}s")
    
    # Re-calculate relative lyrics with the final start
    _, segment_lyrics = find_lyrics_segment(all_lyrics, target_duration=args.duration, start_offset=audio_start)
    
    if not segment_lyrics:
        print(f"No lyrics found in the selected range for {args.post}.")
        return

    for s, e, t in segment_lyrics:
        print(f"  [{s:5.2f} - {e:5.2f}] {t}")

    lib_broll = BrollLibrary(broll_dir=paths.broll_dir, ffmpeg_path=bins.ffmpeg, ffprobe_path=bins.ffprobe)
    lib_library = BrollLibrary(broll_dir=str(Path(paths.project_root) / "broll_library"), 
                               ffmpeg_path=bins.ffmpeg, ffprobe_path=bins.ffprobe)
    
    metas = lib_broll.load_theme(spec.themes)
    metas += lib_library.load_theme(spec.themes)
    
    if not metas:
        print(f"No b-roll found for themes: {spec.themes} in broll/ or broll_library/")
        return

    # 4. Build Edit Plan
    # Seed based on post name and start time
    seed = hash(args.post + str(audio_start)) % (2**31)
    
    # Prioritize themes from spec, fallback to city_drive if empty
    effective_themes = spec.themes if spec.themes else ["city_drive"]
    print(f"Using themes for lyrics mode: {effective_themes}")
    
    metas = lib_library.load_theme(effective_themes)
    if not metas:
        metas = lib_broll.load_theme(effective_themes)
    
    if not metas:
        print(f"No b-roll found for themes: {effective_themes} in broll/ or broll_library/")
        return
        
    plan = build_edit_plan(metas=metas, beat=beats, cfg=cfg, seed=seed)

    # 5. Export
    out_dir = post_dir / "output_lyrics"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "tiktok_lyrics.mp4"
    
    # Overlay text: disabled as per user request
    overlay_text = None

    print(f"Rendering to: {out_path} (Overlay: None)")
    export_video_fast(
        ffmpeg_path=bins.ffmpeg,
        gpu=gpu,
        plan=plan,
        audio_path=str(track_path),
        audio_start_offset=audio_start,
        out_path=str(out_path),
        cfg=cfg,
        overlay_text=overlay_text,
        lyrics=segment_lyrics
    )
    
    print(f"\n✅ Done! Video saved at: {out_path}")

if __name__ == "__main__":
    main()
