from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from PIL import Image

from core.config import RenderConfig
from logic.editor import EditPlan
from core.ffmpeg_utils import run_ffmpeg
from core.gpu import GpuPlan


@dataclass(frozen=True)
class ExportResult:
    output_path: str


def _vf_style(cfg: RenderConfig) -> str:
    parts = [
        # Fill 9:16 with center-crop after scaling
        f"scale=w={cfg.width}:h={cfg.height}:force_original_aspect_ratio=increase",
        f"crop=w={cfg.width}:h={cfg.height}",
        "setsar=1",
        f"fps={cfg.fps}",
        "format=yuv420p",
        # Add a black background color to fill empty areas
        "color=color=black:size={cfg.width}x{cfg.height}:d=1 [bg]; [bg][0:v] overlay=shortest=1"
    ]
    # Skip expensive filters for faster encoding
    if cfg.contrast != 1.0 or cfg.saturation != 1.0:
        parts.insert(4, f"eq=contrast={cfg.contrast}:saturation={cfg.saturation}")
    if cfg.enable_grain:
        parts.append(f"noise=alls={cfg.grain_strength}:allf=t")
    return ",".join(parts)


def get_dominant_color(image_path: str) -> str:
    """Calcula a cor predominante de uma imagem e retorna no formato hexadecimal."""
    with Image.open(image_path) as img:
        img = img.resize((50, 50))  # Reduz o tamanho para acelerar o cálculo
        pixels = img.getdata()
        r, g, b = map(lambda x: int(sum(x) / len(x)), zip(*pixels))
        return f"#{r:02x}{g:02x}{b:02x}"


def export_video(
    ffmpeg_path: str,
    gpu: GpuPlan,
    plan: EditPlan,
    audio_path: str,
    audio_start_offset: float,
    out_path: str,
    cfg: RenderConfig,
    overlay_text: str | None = None,
) -> ExportResult:
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)

    # Inputs: one per segment + audio
    input_args: list[str] = []
    for seg in plan.segments:
        if gpu.hwaccel:
            input_args += ["-hwaccel", gpu.hwaccel]
            if gpu.hwaccel_output_format:
                input_args += ["-hwaccel_output_format", gpu.hwaccel_output_format]
        
        is_image = Path(seg.src).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        if is_image:
            input_args += ["-loop", "1"]
            
            bg_color = get_dominant_color(seg.src)

        input_args += ["-i", seg.src]

    input_args += ["-i", audio_path]

    vf_style = _vf_style(cfg)

    # Filter graph: per clip trim + speed + style, concat, audio trim
    fc_parts: list[str] = []
    v_labels: list[str] = []

    for i, seg in enumerate(plan.segments):
        v_in = f"[{i}:v]"
        v_out = f"v{i}"

        # setpts speed: output PTS divided by speed (faster motion for >1.0)
        # We trimmed input duration as out_dur * speed so final length is out_dur
        chain = (
            f"trim=start={seg.in_start}:duration={seg.in_dur},"
            f"setpts=(PTS-STARTPTS)/{seg.speed},"
            f"{vf_style}"
        )
        
        if overlay_text:
            # TikTok Hook Style: Respect safe areas, clean font
            clean_text = overlay_text.upper().replace("'", "").replace(":", "")
            # Limiting to 3-6 words as requested in logic if possible, 
            # but usually overlay_text is already short.
            
            # Spaces between letters for premium look
            tracked_text = " ".join(list(clean_text))
            font_path = "C\\:/Windows/Fonts/bahnschrift.ttf"
            
            # Margins from config
            m_lat = cfg.width * cfg.margin_lateral
            m_top = cfg.height * cfg.margin_top
            m_bot = cfg.height * cfg.margin_bottom
            
            # Constraints:
            # x center: (w-text_w)/2
            # y top-third: (h-text_h)/3
            # Current y is centered at 1/3 of the height (Rule of Thirds)
            # We also ensure fontsize doesn't overflow width
            
            chain += (
                f",drawtext=text='{tracked_text}':fontfile='{font_path}':fontcolor=white:"
                f"fontsize='min(70, (w-{2*m_lat})*25/text_w)':" # Scale down if too wide
                f"x=(w-text_w)/2:y=(h-text_h)/3:" 
                f"shadowcolor=black@0.7:shadowx=4:shadowy=4"
            )

        fc_parts.append(f"{v_in}{chain}[{v_out}]")
        v_labels.append(f"[{v_out}]")

    # Concat
    concat_in = "".join(v_labels)
    fc_parts.append(f"{concat_in}concat=n={len(v_labels)}:v=1:a=0[vout]")

    # Audio: trim from first beat offset, match duration
    a_in = f"[{len(plan.segments)}:a]"
    fc_parts.append(
        f"{a_in}atrim=start={max(0.0, audio_start_offset)}:duration={plan.duration},asetpts=PTS-STARTPTS[aout]"
    )

    filter_complex = ";".join(fc_parts)

    # Encoder settings
    v_codec = gpu.video_encoder
    enc_args: list[str] = []

    if v_codec == "h264_nvenc":
        enc_args += [
            "-c:v",
            "h264_nvenc",
            "-preset",
            cfg.nvenc_preset,
            "-profile:v",
            "high",
            "-rc:v",
            "vbr",  # vbr_hq is slower, vbr is faster
            "-b:v",
            cfg.video_bitrate,
            "-maxrate:v",
            cfg.maxrate,
            "-bufsize:v",
            cfg.bufsize,
            "-pix_fmt",
            "yuv420p",
            "-gpu",
            "0",  # Force GPU 0
            "-delay",
            "0",  # No B-frames delay
            "-zerolatency",
            "1",  # Optimize for low latency
        ]
    else:
        enc_args += [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-profile:v",
            "high",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
        ]

    args = [
        "-hide_banner",
        "-y",
        "-nostdin",
        "-stats",
        "-threads",
        "0",  # Auto-detect CPU threads for filter_complex
        "-filter_threads",
        "0",  # Parallel filter processing
        *input_args,
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-r",
        str(cfg.fps),
        *enc_args,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(outp),
    ]

    # Ensure stable temp env for FFmpeg on Windows
    os.environ.setdefault("FFREPORT", "")

    run_ffmpeg(ffmpeg_path, args)
    return ExportResult(output_path=str(outp))
