from __future__ import annotations

from dataclasses import dataclass

from core.ffmpeg_utils import list_ffmpeg_encoders, list_ffmpeg_filters, list_ffmpeg_hwaccels


@dataclass(frozen=True)
class GpuPlan:
    hwaccel: str | None
    hwaccel_output_format: str | None
    video_encoder: str
    supports_nvenc: bool


def detect_gpu_plan(ffmpeg_path: str) -> GpuPlan:
    enc = list_ffmpeg_encoders(ffmpeg_path)
    hw = list_ffmpeg_hwaccels(ffmpeg_path)

    supports_nvenc = "h264_nvenc" in enc
    if supports_nvenc:
        encoder = "h264_nvenc"
    else:
        encoder = "libx264"

    # IMPORTANT: We keep decode on CPU by default.
    # Our filtergraph uses CPU filters (scale/crop/eq/noise/concat). If we request
    # GPU frame output (hwaccel_output_format=cuda), FFmpeg may fail to auto-convert.
    # We still use NVENC for encode when available.
    hwaccel = None
    hwaccel_output_format = None

    return GpuPlan(
        hwaccel=hwaccel,
        hwaccel_output_format=hwaccel_output_format,
        video_encoder=encoder,
        supports_nvenc=supports_nvenc,
    )


def has_filter(ffmpeg_path: str, name: str) -> bool:
    return f" {name} " in list_ffmpeg_filters(ffmpeg_path)
