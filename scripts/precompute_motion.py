#!/usr/bin/env python3
"""Precompute motion scores for all videos in broll_library."""
from pathlib import Path
import subprocess
import numpy as np
from logic.broll_loader import BrollLibrary, ClipMeta
from core.ffmpeg_utils import ensure_ffmpeg

def main():
    project_root = Path(__file__).parent
    broll_dir = project_root / "broll_library"
    tools_dir = project_root / "tools"
    
    bins = ensure_ffmpeg(str(tools_dir))
    lib = BrollLibrary(
        broll_dir=str(broll_dir),
        ffmpeg_path=bins.ffmpeg,
        ffprobe_path=bins.ffprobe
    )
    
    # Get all video files
    all_files = []
    for subdir in broll_dir.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("_"):
            for vf in subdir.glob("*.mp4"):
                all_files.append(str(vf.resolve()))
            for vf in subdir.glob("*.webm"):
                all_files.append(str(vf.resolve()))
            for vf in subdir.glob("*.mov"):
                all_files.append(str(vf.resolve()))
    
    all_files = list(dict.fromkeys(all_files))
    print(f"📊 Found {len(all_files)} video files in broll_library/")
    
    # Load cache
    lib._load_cache()
    
    to_process = []
    for path in all_files:
        cached = lib._cache.get(path, {})
        if not cached.get("motion_computed"):
            to_process.append(path)
    
    print(f"🎬 Need to compute motion for {len(to_process)} videos")
    print(f"✅ Already cached: {len(all_files) - len(to_process)} videos")
    
    if not to_process:
        print("\n✨ All videos already have motion scores!")
        return
    
    print("\nStarting motion computation...\n")
    
    for i, path in enumerate(to_process, 1):
        name = Path(path).name
        print(f"[{i}/{len(to_process)}] {name}...", end=" ", flush=True)
        
        try:
            # Probe metadata first
            if path not in lib._metas:
                meta = lib._probe_meta(path)
                if not meta:
                    print("❌ No video stream")
                    continue
                lib._metas[path] = meta
            
            # Compute motion
            motion = lib._estimate_motion(path, seconds=1.0)
            
            # Update meta
            meta = lib._metas[path]
            lib._metas[path] = ClipMeta(
                path=meta.path,
                duration=meta.duration,
                width=meta.width,
                height=meta.height,
                fps=meta.fps,
                motion=motion
            )
            
            # Save to cache
            p = Path(path)
            try:
                st = p.stat()
                size = int(st.st_size)
                mtime_ns = int(st.st_mtime_ns)
            except Exception:
                size = -1
                mtime_ns = -1
            
            lib._cache[path] = {
                "duration": meta.duration,
                "width": meta.width,
                "height": meta.height,
                "fps": meta.fps,
                "motion": motion,
                "motion_computed": True,
                "size": size,
                "mtime_ns": mtime_ns,
            }
            
            print(f"✅ motion={motion:.3f}")
            
            # Save cache every 10 videos
            if i % 10 == 0:
                lib._save_cache()
                print(f"  💾 Cache saved ({i}/{len(to_process)})")
        
        except Exception as ex:
            print(f"❌ Error: {ex}")
    
    # Final save
    lib._save_cache()
    print(f"\n✨ Complete! Motion scores computed for {len(to_process)} videos")
    print(f"📁 Cache saved to: {lib.cache_path}")

if __name__ == "__main__":
    main()
