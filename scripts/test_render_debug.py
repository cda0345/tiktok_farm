"""Debug test for render process."""
from pathlib import Path
import sys

print("=" * 80)
print("DEBUG TEST - Render Process")
print("=" * 80)

# Step 1: Imports
print("\n[1/8] Importing modules...")
try:
    from core.audio_handler import analyze_beats
    from logic.broll_loader import BrollLibrary
    from core.config import PathsConfig, RenderConfig
    from logic.editor import build_edit_plan
    from logic.exporter_fast import export_video_fast as export_video
    from core.ffmpeg_utils import ensure_ffmpeg
    from core.gpu import detect_gpu_plan
    from logic.post_parser import parse_caption_file
    print("  ✅ All imports successful")
except Exception as e:
    print(f"  ❌ Import error: {e}")
    sys.exit(1)

# Step 2: Setup paths
print("\n[2/8] Setting up paths...")
project_root = Path(__file__).resolve().parent.parent
paths = PathsConfig(
    project_root=str(project_root),
    broll_dir="broll_library",
    posts_dir="posts",
    audio_dir="audio/tracks",
    tools_dir="tools",
).with_resolved_paths()

print(f"  Project root: {paths.project_root}")
print(f"  Broll dir: {paths.broll_dir}")
print(f"  Posts dir: {paths.posts_dir}")

# Step 3: FFmpeg
print("\n[3/8] Checking FFmpeg...")
try:
    bins = ensure_ffmpeg(paths.tools_dir)
    print(f"  ✅ FFmpeg: {bins.ffmpeg}")
    print(f"  ✅ FFprobe: {bins.ffprobe}")
except Exception as e:
    print(f"  ❌ FFmpeg error: {e}")
    sys.exit(1)

# Step 4: GPU
print("\n[4/8] Detecting GPU...")
try:
    gpu = detect_gpu_plan(bins.ffmpeg)
    print(f"  ✅ Encoder: {gpu.video_encoder}")
except Exception as e:
    print(f"  ❌ GPU error: {e}")
    sys.exit(1)

# Step 5: Parse post
print("\n[5/8] Parsing post_001...")
post_dir = str(Path(paths.posts_dir) / "post_001_peggy_gou_nanana")
try:
    spec = parse_caption_file(post_dir)
    print(f"  ✅ Track ID: {spec.track_id}")
    print(f"  ✅ Themes: {spec.themes}")
except Exception as e:
    print(f"  ❌ Parse error: {e}")
    sys.exit(1)

# Step 6: Audio analysis
print("\n[6/8] Analyzing audio...")
track_path = str(Path(paths.audio_dir) / f"{spec.track_id}.mp3")
try:
    beats = analyze_beats(track_path)
    print(f"  ✅ BPM: {beats.bpm:.1f}")
    print(f"  ✅ Start offset: {beats.start_offset:.2f}s")
    print(f"  ✅ Beats detected: {len(beats.beats)}")
except Exception as e:
    print(f"  ❌ Audio analysis error: {e}")
    sys.exit(1)

# Step 7: Load B-roll
print("\n[7/8] Loading B-roll library...")
try:
    lib = BrollLibrary(broll_dir=paths.broll_dir, ffmpeg_path=bins.ffmpeg, ffprobe_path=bins.ffprobe)
    print(f"  Library initialized")
    
    print(f"  Loading themes: {spec.themes}")
    metas = lib.load_theme(spec.themes)
    print(f"  ✅ B-roll clips found: {len(metas)}")
    
    if len(metas) < 2:
        print(f"  ❌ Not enough clips!")
        sys.exit(1)
except Exception as e:
    print(f"  ❌ B-roll error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 8: Build edit plan
print("\n[8/8] Building edit plan...")
cfg = RenderConfig()
try:
    import hashlib
    h = hashlib.sha256("test_debug".encode("utf-8")).digest()
    seed = int.from_bytes(h[:8], "big", signed=False) % (2**31 - 1)
    
    print(f"  Seed: {seed}")
    print(f"  Max duration: {cfg.max_duration_s}s")
    print(f"  BPM: {beats.bpm}")
    
    print(f"  Calling build_edit_plan...")
    plan = build_edit_plan(metas=metas, beat=beats, cfg=cfg, seed=seed)
    
    print(f"  ✅ Plan created!")
    print(f"  ✅ Segments: {len(plan.segments)}")
    print(f"  ✅ Total duration: {plan.duration:.2f}s")
    
    # Show segment details
    print(f"\n  Segment breakdown:")
    for i, seg in enumerate(plan.segments[:5]):  # Show first 5
        print(f"    {i+1}. {Path(seg.src).name}: {seg.out_dur:.2f}s")
    if len(plan.segments) > 5:
        print(f"    ... and {len(plan.segments) - 5} more")
    
except Exception as e:
    print(f"  ❌ Edit plan error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED - Ready to render!")
print("=" * 80)
print("\nNow testing render (1 segment only for speed)...")

# Test render with just 1 segment
out_dir = Path(post_dir) / "output"
out_dir.mkdir(parents=True, exist_ok=True)
test_out = str(out_dir / "test_debug.mp4")

try:
    # Create a minimal plan with just 1 segment for testing
    from logic.editor import EditPlan, Segment
    test_plan = EditPlan(
        segments=plan.segments[:1],  # Just first segment
        duration=plan.segments[0].out_dur,
        used_videos=[plan.segments[0].src]
    )
    
    print(f"\nRendering test video with 1 segment...")
    print(f"  Output: {test_out}")
    
    export_video(
        ffmpeg_path=bins.ffmpeg,
        gpu=gpu,
        plan=test_plan,
        audio_path=track_path,
        audio_start_offset=beats.start_offset,
        out_path=test_out,
        cfg=cfg,
    )
    
    print(f"\n✅ TEST RENDER COMPLETE!")
    print(f"Check: {test_out}")
    
except Exception as e:
    print(f"\n❌ Render error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
