"""Fast 2-pass exporter: pre-render segments then concat."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import platform

from core.config import RenderConfig
from logic.editor import EditPlan
from core.ffmpeg_utils import run_ffmpeg
from core.gpu import GpuPlan


@dataclass(frozen=True)
class ExportResult:
    output_path: str


def _render_segment_fast(
    ffmpeg_path: str,
    gpu: GpuPlan,
    src: str,
    in_start: float,
    in_dur: float,
    speed: float,
    out_file: str,
    cfg: RenderConfig,
    overlay_text: str | None = None,
    lyrics_events: list[tuple[float, float, str]] | None = None,
) -> str:
    """Render one segment to temp file. Returns path."""
    
    is_image = Path(src).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

    # Single input, simple filter chain, immediate GPU encode
    args = ["-hide_banner", "-y", "-nostdin"]
    
    if is_image:
        args += ["-loop", "1"]
        
    vf = (
        f"setpts=PTS/{speed},"
        f"scale=w={cfg.width}:h={cfg.height}:force_original_aspect_ratio=increase,"
        f"crop=w={cfg.width}:h={cfg.height},"
        "setsar=1,"
        f"fps={cfg.fps},"
        "format=yuv420p"
    )
    
    font_path = "C\\:/Windows/Fonts/bahnschrift.ttf"
    if platform.system().lower() == "darwin":
        # Standard macOS font path for a bold/clean font
        font_path = "/System/Library/Fonts/Supplemental/Futura-CondensedExtraBold.ttf"
        if not Path(font_path).exists():
             font_path = "/System/Library/Fonts/Helvetica.ttc"

    def wrap_text(text: str, max_chars: int = 25) -> str:
        """Simple text wrapping at word boundaries."""
        words = text.split()
        lines = []
        curr_line = []
        curr_len = 0
        for w in words:
            if curr_len + len(w) > max_chars and curr_line:
                lines.append(" ".join(curr_line))
                curr_line = [w]
                curr_len = len(w)
            else:
                curr_line.append(w)
                curr_len += len(w) + 1
        if curr_line:
            lines.append(" ".join(curr_line))
        return "\n".join(lines)

    if overlay_text:
        # TikTok Hook Style: Respect safe areas, clean font
        clean_text = overlay_text.upper().replace("'", "").replace(":", "")
        wrapped_hook = wrap_text(clean_text, max_chars=20)
        # We use a slightly smaller default fontsize (60) and place at top-third.
        vf += (
            f",drawtext=text='{wrapped_hook}':fontfile='{font_path}':fontcolor=white:fontsize=75:"
            f"x=(w-text_w)/2:y=(h-text_h)/3:shadowcolor=black@0.7:shadowx=4:shadowy=4:line_spacing=10"
        )
    
    if lyrics_events:
        for l_start, l_end, l_text in lyrics_events:
            clean_l = l_text.upper().replace("'", "").replace(":", "")
            wrapped_l = wrap_text(clean_l, max_chars=25)
            # Lyrics style: centered, bottom third, bold/impactful but clean
            vf += (
                f",drawtext=text='{wrapped_l}':fontfile='{font_path}':fontcolor=white:fontsize=65:"
                f"x=(w-text_w)/2:y=(h-text_h)*0.8:shadowcolor=black@0.8:shadowx=3:shadowy=3:"
                f"enable='between(t,{l_start:.3f},{l_end:.3f})':line_spacing=5"
            )

    args += [
        "-ss", str(in_start),
        "-t", str(in_dur),
        "-i", src,
        "-vf", vf,
    ]
    
    if gpu.video_encoder == "h264_nvenc":
        args += [
            "-c:v", "h264_nvenc",
            "-preset", "p1",  # Fastest
            "-rc:v", "vbr",
            "-b:v", cfg.video_bitrate,
            "-pix_fmt", "yuv420p",
        ]
    else:
        args += [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
        ]
    
    args += ["-an", out_file]  # No audio in segments
    
    run_ffmpeg(ffmpeg_path, args, stream_output=False)
    return out_file


def _save_edit_plan_json(plan: EditPlan, out_path: str, variant_name: str = "v1") -> None:
    """Save edit plan as JSON for reference."""
    json_path = Path(out_path).parent / f"{variant_name}_plan.json"
    
    plan_data = {
        "duration": plan.duration,
        "total_segments": len(plan.segments),
        "segments": [
            {
                "index": i,
                "src_file": Path(seg.src).name,
                "src_full_path": seg.src,
                "in_start": seg.in_start,
                "in_dur": seg.in_dur,
                "speed": seg.speed,
                "out_dur": seg.out_dur,
            }
            for i, seg in enumerate(plan.segments)
        ],
    }
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2, ensure_ascii=False)


def export_video_fast(
    ffmpeg_path: str,
    gpu: GpuPlan,
    plan: EditPlan,
    audio_path: str,
    audio_start_offset: float,
    out_path: str,
    cfg: RenderConfig,
    max_workers: int = 1,  # Changed to sequential for stability
    overlay_text: str | None = None,
    lyrics: list[tuple[float, float, str]] | None = None,
) -> ExportResult:
    """Fast 2-pass: segment render + concat.
    
    lyrics: list of (global_start, global_end, text)
    """
    
    print("=" * 60)
    print("🚀 USING FAST 2-PASS EXPORTER (exporter_fast.py)")
    print("=" * 60)
    
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    
    # Save edit plan as JSON
    variant_name = outp.stem  # e.g., "v1", "v2", "v3"
    _save_edit_plan_json(plan, out_path, variant_name)
    
    temp_dir = Path(tempfile.gettempdir()) / "insta_render"
    temp_dir.mkdir(exist_ok=True)
    
    print(f"[Pass 1/2] Rendering {len(plan.segments)} segments...")
    
    # Pass 1: Render segments SEQUENTIALLY (more stable)
    segment_files = []
    
    current_global_time = 0.0
    for i, seg in enumerate(plan.segments):
        seg_file = str(temp_dir / f"seg_{i:03d}.mp4")
        print(f"  Segment {i+1}/{len(plan.segments)}: {Path(seg.src).name} ({seg.out_dur:.2f}s)...", end=" ", flush=True)
        
        # Calculate local lyrics for this segment
        seg_lyrics = []
        if lyrics:
            seg_end = current_global_time + seg.out_dur
            for l_start, l_end, l_text in lyrics:
                # Does lyric overlap with [current_global_time, seg_end]?
                overlap_start = max(current_global_time, l_start)
                overlap_end = min(seg_end, l_end)
                
                if overlap_start < overlap_end:
                    # Convert to local time (relative to segment start)
                    local_start = overlap_start - current_global_time
                    local_end = overlap_end - current_global_time
                    seg_lyrics.append((local_start, local_end, l_text))
        
        try:
            _render_segment_fast(
                ffmpeg_path,
                gpu,
                seg.src,
                seg.in_start,
                seg.in_dur,
                seg.speed,
                seg_file,
                cfg,
                overlay_text=overlay_text,
                lyrics_events=seg_lyrics if seg_lyrics else None
            )
            segment_files.append((i, seg_file))
            print("✅")
        except Exception as ex:
            print(f"❌ ERROR: {ex}")
            raise
        
        current_global_time += seg.out_dur
    
    # Sort by index
    segment_files.sort(key=lambda x: x[0])
    sorted_files = [f for _, f in segment_files]
    
    print(f"\n[Pass 2/2] Concatenating {len(sorted_files)} segments + audio...")
    
    # Pass 2: Concat segments + add audio (super fast, no re-encode)
    concat_list = temp_dir / "concat.txt"
    with open(concat_list, "w") as f:
        for sf in sorted_files:
            f.write(f"file '{sf}'\n")
    
    # Final concat with audio
    args = [
        "-hide_banner",
        "-y",
        "-nostdin",
        "-ss", str(max(0.0, audio_start_offset)),
        "-i", audio_path,
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-map", "1:v:0",
        "-map", "0:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(plan.duration),
        "-shortest",
        "-movflags", "+faststart",
        str(outp),
    ]
    
    run_ffmpeg(ffmpeg_path, args, stream_output=True)
    
    # Cleanup
    for _, seg_file in segment_files:
        try:
            os.unlink(seg_file)
        except Exception:
            pass
    try:
        os.unlink(concat_list)
    except Exception:
        pass
    
    print(f"✅ Video complete: {outp.name}")
    return ExportResult(output_path=str(outp))
