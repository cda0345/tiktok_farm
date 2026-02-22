#!/usr/bin/env python3
"""Gera um post RAW sem overlay, intercalando video e imagens de um post pack.

Fluxo:
1) Lê arquivos em `<post_dir>/raw/video` e `<post_dir>/raw/images`.
2) Monta uma timeline alternando trechos de vídeo e fotos.
3) Aplica zoom sutil nas fotos estáticas.
4) Exporta o vídeo final em 9:16 (1080x1920), sem overlay.
5) Envia o resultado para Telegram (opcional).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")
load_dotenv()

import sys

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.ffmpeg_utils import ensure_ffmpeg, ffprobe_json, run_ffmpeg


VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
FPS = 30000 / 1001
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920


@dataclass(frozen=True)
class Segment:
    kind: str  # "video" | "image"
    source: Path
    duration: float
    start: float = 0.0


@dataclass(frozen=True)
class ImageInfo:
    path: Path
    width: int
    height: int


def _video_duration_s(ffprobe_path: str, file_path: Path) -> float:
    probe = ffprobe_json(ffprobe_path, str(file_path))
    duration = ((probe.get("format") or {}).get("duration")) or "0"
    try:
        return max(0.0, float(duration))
    except Exception:
        return 0.0


def _pick_primary_video(ffprobe_path: str, videos: list[Path]) -> tuple[Path, float]:
    best_path: Path | None = None
    best_duration = -1.0
    for path in videos:
        duration = _video_duration_s(ffprobe_path, path)
        if duration > best_duration:
            best_duration = duration
            best_path = path
    if best_path is None:
        raise RuntimeError("Nenhum vídeo válido encontrado em raw/video.")
    return best_path, best_duration


def _read_image_info(ffprobe_path: str, image_path: Path) -> ImageInfo | None:
    try:
        probe = ffprobe_json(ffprobe_path, str(image_path))
        streams = probe.get("streams") or []
        if not streams:
            return None
        stream = streams[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if width <= 0 or height <= 0:
            return None
        return ImageInfo(path=image_path, width=width, height=height)
    except Exception:
        return None


def _collect_media(post_dir: Path, *, ffprobe_path: str) -> tuple[list[Path], list[Path]]:
    raw_video_dir = post_dir / "raw" / "video"
    raw_image_dir = post_dir / "raw" / "images"
    if not raw_video_dir.exists():
        raise RuntimeError(f"Pasta não encontrada: {raw_video_dir}")
    if not raw_image_dir.exists():
        raise RuntimeError(f"Pasta não encontrada: {raw_image_dir}")

    videos = sorted(
        p for p in raw_video_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS and p.stat().st_size > 250 * 1024
    )
    raw_images = sorted(
        p for p in raw_image_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.stat().st_size > 20 * 1024
    )
    image_infos = [info for info in (_read_image_info(ffprobe_path, p) for p in raw_images) if info]

    # Evita imagens muito pequenas/baixa qualidade que tendem a ficar ruins no frame vertical.
    qualified = [
        info
        for info in image_infos
        if (info.width * info.height) >= 700_000 and info.width >= 900 and info.height >= 500
    ]
    pool = qualified if len(qualified) >= 2 else image_infos
    pool = sorted(pool, key=lambda i: (i.width * i.height), reverse=True)
    images = [info.path for info in pool]
    return videos, images


def _build_segments(
    *,
    duration_s: float,
    video_path: Path,
    video_duration_s: float,
    images: list[Path],
) -> list[Segment]:
    if duration_s <= 0:
        raise RuntimeError("Duração do post deve ser maior que zero.")

    max_images = min(3, len(images))
    if max_images <= 0:
        return [Segment(kind="video", source=video_path, duration=duration_s, start=0.0)]

    image_duration = 1.15
    while max_images > 0 and (duration_s - (max_images * image_duration)) < 4.2:
        max_images -= 1

    if max_images <= 0:
        return [Segment(kind="video", source=video_path, duration=duration_s, start=0.0)]

    video_slots = max_images + 1
    total_image_time = max_images * image_duration
    total_video_time = max(0.8, duration_s - total_image_time)
    base_video_duration = total_video_time / video_slots

    video_durations: list[float] = [base_video_duration] * video_slots
    correction = duration_s - (sum(video_durations) + total_image_time)
    video_durations[-1] += correction

    max_seg = max(video_durations)
    available = max(0.0, video_duration_s - max_seg)
    starts: list[float] = []
    if video_slots == 1:
        starts = [0.0]
    else:
        for idx in range(video_slots):
            starts.append(available * idx / (video_slots - 1))

    segs: list[Segment] = []
    for idx in range(video_slots):
        segs.append(
            Segment(
                kind="video",
                source=video_path,
                duration=max(0.45, video_durations[idx]),
                start=max(0.0, starts[idx]),
            )
        )
        if idx < max_images:
            segs.append(
                Segment(
                    kind="image",
                    source=images[idx],
                    duration=image_duration,
                    start=0.0,
                )
            )
    return segs


def _render_video_segment(ffmpeg_path: str, segment: Segment, output_path: Path) -> None:
    vf = (
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},setsar=1,format=yuv420p"
    )
    args = [
        "-y",
        "-ss",
        f"{segment.start:.3f}",
        "-i",
        str(segment.source),
        "-t",
        f"{segment.duration:.3f}",
        "-an",
        "-vf",
        vf,
        "-r",
        "30000/1001",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    run_ffmpeg(ffmpeg_path, args, stream_output=False)


def _render_image_segment(ffmpeg_path: str, segment: Segment, output_path: Path, *, zoom_amount: float) -> None:
    # Preserva proporção da foto no foreground e usa fundo blur para preencher o 9:16.
    frame_count = max(2, int(round(segment.duration * FPS)))
    denom = max(1, frame_count - 1)
    internal_w = OUTPUT_WIDTH * 2
    internal_h = OUTPUT_HEIGHT * 2
    zoom_expr = f"1+{zoom_amount:.6f}*n/{denom}"
    fc = (
        "[0:v]split=2[bgin][fgin];"
        "[bgin]scale="
        f"{OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},boxblur=28:12[bg];"
        "[fgin]scale="
        f"{OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"scale={internal_w}:{internal_h}:flags=lanczos,"
        "scale="
        f"w='trunc({internal_w}*({zoom_expr})/2)*2':"
        f"h='trunc({internal_h}*({zoom_expr})/2)*2':"
        "eval=frame,"
        f"crop={internal_w}:{internal_h}:(in_w-{internal_w})/2:(in_h-{internal_h})/2,"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:flags=lanczos,"
        "setsar=1,format=yuv420p[vout]"
    )
    args = [
        "-y",
        "-loop",
        "1",
        "-framerate",
        "30000/1001",
        "-t",
        f"{segment.duration:.3f}",
        "-i",
        str(segment.source),
        "-an",
        "-filter_complex",
        fc,
        "-map",
        "[vout]",
        "-frames:v",
        str(frame_count),
        "-r",
        "30000/1001",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    run_ffmpeg(ffmpeg_path, args, stream_output=False)


def _concat_segments(ffmpeg_path: str, segment_files: list[Path], output_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="raw_post_concat_") as tmp_dir:
        list_path = Path(tmp_dir) / "concat.txt"
        lines = [f"file '{p.resolve()}'" for p in segment_files]
        list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        args = [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        run_ffmpeg(ffmpeg_path, args, stream_output=False)


def _send_video_to_telegram(video_path: Path, caption: str) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID não configurados.")
        return False
    if not video_path.exists():
        print(f"⚠️ Vídeo não encontrado para envio: {video_path}")
        return False

    caption_clean = " ".join((caption or "").split())
    if len(caption_clean) > 1024:
        caption_clean = caption_clean[:1020].rsplit(" ", 1)[0] + "..."

    send_video_url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    send_doc_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    for attempt in range(1, 3):
        try:
            with open(video_path, "rb") as video:
                files = {"video": video}
                data = {"chat_id": chat_id, "caption": caption_clean, "supports_streaming": True}
                resp = requests.post(send_video_url, files=files, data=data, timeout=180)
            if resp.status_code == 200:
                print("✅ Vídeo enviado com sucesso para o Telegram.")
                return True
            print(f"⚠️ Tentativa {attempt}/2 falhou no sendVideo: {resp.status_code} - {resp.text[:240]}")
        except Exception as exc:
            print(f"⚠️ Tentativa {attempt}/2 falhou no sendVideo: {exc}")

    try:
        with open(video_path, "rb") as video:
            files = {"document": video}
            data = {"chat_id": chat_id, "caption": caption_clean}
            resp = requests.post(send_doc_url, files=files, data=data, timeout=240)
        if resp.status_code == 200:
            print("✅ Vídeo enviado como documento no Telegram (fallback).")
            return True
        print(f"❌ Falha no fallback sendDocument: {resp.status_code} - {resp.text[:240]}")
        return False
    except Exception as exc:
        print(f"❌ Falha no fallback sendDocument: {exc}")
        return False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera post RAW sem overlay intercalando vídeo e imagens.")
    parser.add_argument("--post-dir", required=True, help="Pasta do post pack (ex: posts/2026-.../)")
    parser.add_argument("--name", default="post_raw_mix", help="Nome base do arquivo de saída (sem extensão).")
    parser.add_argument("--duration", type=float, default=11.0, help="Duração final desejada em segundos.")
    parser.add_argument(
        "--send-telegram",
        action="store_true",
        help="Envia o vídeo final para o Telegram após render.",
    )
    parser.add_argument(
        "--caption",
        default="🎬 POST RAW MIX\nSem overlay • vídeo+fotos",
        help="Caption usada no envio para Telegram.",
    )
    parser.add_argument("--seed", type=int, default=7, help="Seed para pequenas variações de zoom.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    random.seed(args.seed)

    post_dir = Path(args.post_dir).expanduser().resolve()
    if not post_dir.exists():
        raise RuntimeError(f"Pasta não encontrada: {post_dir}")

    output_dir = post_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    ff = ensure_ffmpeg("tools")
    videos, images = _collect_media(post_dir, ffprobe_path=ff.ffprobe)
    if not videos:
        raise RuntimeError("Nenhum vídeo encontrado em raw/video para montar o post raw.")

    primary_video, primary_duration = _pick_primary_video(ff.ffprobe, videos)
    segments = _build_segments(
        duration_s=args.duration,
        video_path=primary_video,
        video_duration_s=primary_duration,
        images=images,
    )
    if not segments:
        raise RuntimeError("Falha ao construir timeline de segmentos.")

    print(f"🎞️ Vídeo base: {primary_video.name} ({primary_duration:.2f}s)")
    print(f"🖼️ Imagens usadas: {min(3, len(images))}")
    if images:
        print("🖼️ Seleção de imagens:")
        for img in images[:3]:
            print(f"   - {img.name}")
    print(f"🧩 Segmentos totais: {len(segments)}")

    temp_files: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="raw_post_segments_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        for idx, seg in enumerate(segments):
            seg_file = tmp_path / f"seg_{idx:02d}.mp4"
            temp_files.append(seg_file)
            if seg.kind == "video":
                _render_video_segment(ff.ffmpeg, seg, seg_file)
            else:
                # Zoom total discreto para evitar sensação de "tremido".
                zoom_amount = random.uniform(0.018, 0.030)
                _render_image_segment(ff.ffmpeg, seg, seg_file, zoom_amount=zoom_amount)

        output_video = output_dir / f"{args.name}.mp4"
        _concat_segments(ff.ffmpeg, temp_files, output_video)

    manifest = {
        "name": args.name,
        "post_dir": str(post_dir),
        "output_video": str((output_dir / f"{args.name}.mp4")),
        "duration_target_s": args.duration,
        "primary_video": str(primary_video),
        "primary_video_duration_s": round(primary_duration, 3),
        "segment_count": len(segments),
        "segments": [
            {
                "kind": s.kind,
                "source": str(s.source),
                "start_s": round(s.start, 3),
                "duration_s": round(s.duration, 3),
            }
            for s in segments
        ],
        "overlay": False,
    }
    manifest_path = output_dir / f"{args.name}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=" * 72)
    print(f"✅ Post RAW gerado: {output_dir / f'{args.name}.mp4'}")
    print(f"🧾 Manifesto: {manifest_path}")
    print("=" * 72)

    if args.send_telegram:
        _send_video_to_telegram(output_dir / f"{args.name}.mp4", args.caption)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
