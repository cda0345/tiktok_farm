#!/usr/bin/env python3
"""
Script auxiliar para criar novos posts de fofoca com vídeo.

Uso:
    python3 scripts/create_new_video_post.py \
        --url "https://x.com/user/status/123" \
        --hook "TRETA!!" \
        --headline "TEXTO DA NOTICIA AQUI"
"""

import argparse
import json
import re
import sys
import subprocess
import textwrap
import time
from pathlib import Path

# Adiciona o diretório scripts ao path
sys.path.insert(0, str(Path(__file__).parent))
from create_gossip_post import _render_short_video, _send_video_to_telegram, _get_random_cta, _build_tarja_text


def _build_video_download_candidates(url: str) -> list[str]:
    """Build candidate URLs for X/Twitter to reduce extractor transient failures."""
    raw = (url or "").strip()
    if not raw:
        return []

    candidates: list[str] = [raw]
    is_x = "x.com/" in raw
    is_twitter = "twitter.com/" in raw

    if is_x:
        candidates.append(raw.replace("x.com/", "twitter.com/", 1))
    elif is_twitter:
        candidates.append(raw.replace("twitter.com/", "x.com/", 1))

    status_match = re.search(r"/status/(\d+)", raw)
    if status_match:
        status_id = status_match.group(1)
        candidates.extend(
            [
                f"https://x.com/i/status/{status_id}",
                f"https://twitter.com/i/status/{status_id}",
            ]
        )

    ordered_unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            ordered_unique.append(candidate)
            seen.add(candidate)
    return ordered_unique


def _download_video_with_fallback(video_url: str, output_path: Path) -> None:
    """Download using yt-dlp with retries and URL fallbacks for X/Twitter."""
    candidates = _build_video_download_candidates(video_url)
    if not candidates:
        raise RuntimeError("URL de vídeo vazia")

    def _run_download(candidate_url: str, extractor_api: str | None = None) -> subprocess.CompletedProcess:
        cmd = [
            "yt-dlp",
            "-S",
            "res,ext:mp4:m4a",
            "-f",
            "bv*+ba/best",
            "--merge-output-format",
            "mp4",
            "--no-warnings",
            "--retries",
            "8",
            "--fragment-retries",
            "8",
            "--extractor-retries",
            "8",
            "--retry-sleep",
            "http:2:8",
            "--retry-sleep",
            "fragment:2:8",
        ]
        if extractor_api:
            cmd.extend(["--extractor-args", f"twitter:api={extractor_api}"])
        cmd.extend(["-o", str(output_path), candidate_url])
        return subprocess.run(cmd, capture_output=True, text=True)

    last_error = "erro desconhecido"
    for index, candidate in enumerate(candidates, start=1):
        print(f"⬇️ Tentativa {index}/{len(candidates)}: {candidate}")
        result = _run_download(candidate)

        err_text = ((result.stderr or "").strip() or (result.stdout or "").strip())
        if result.returncode != 0 and "Error(s) while querying API" in err_text:
            print("⚠️ API padrão do X falhou; tentando modo syndication...")
            result = _run_download(candidate, extractor_api="syndication")

        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 100 * 1024:
            return

        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        combined = stderr or stdout or f"yt-dlp retornou código {result.returncode}"
        last_error = combined[-1200:]

        if output_path.exists() and output_path.stat().st_size <= 100 * 1024:
            try:
                output_path.unlink()
            except OSError:
                pass

        if index < len(candidates):
            time.sleep(min(2 * index, 6))

    raise RuntimeError(f"Falha ao baixar vídeo após {len(candidates)} tentativas: {last_error}")


def _send_document_to_telegram(file_path: Path, caption: str) -> bool:
    """Envia um arquivo (document) para o Telegram (ex: vídeo original)."""
    # Importa do create_gossip_post para manter token/chat id centralizados.
    import os
    import requests

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or ""
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or ""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID não configurados")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
            r = requests.post(url, files=files, data=data, timeout=180)
            return r.status_code == 200
    except Exception:
        return False


def preview_text(text: str):
    """Mostra preview de como o texto será quebrado."""
    if text.endswith("..."):
        text = text[:-3].rstrip()
    
    lines = textwrap.wrap(text, width=32, break_long_words=False, break_on_hyphens=False)[:10]
    
    print("\n" + "=" * 70)
    print("📝 PREVIEW DO TEXTO NO VÍDEO")
    print("=" * 70)
    print(f"Caracteres: {len(text)}")
    print(f"Linhas: {len(lines)}/10")
    
    full_lines = textwrap.wrap(text, width=32, break_long_words=False, break_on_hyphens=False)
    if len(full_lines) > 10:
        print(f"⚠️  AVISO: Texto será cortado! ({len(full_lines)} linhas total)")
    else:
        print("✅ Texto completo caberá no vídeo")
    
    print("\nTexto renderizado:")
    print("-" * 70)
    for i, line in enumerate(lines, 1):
        print(f"{i:2}. {line}")
    print("-" * 70 + "\n")
    
    return len(full_lines) <= 10


def _normalize_editorial_hook(hook: str) -> str:
    words = [w for w in " ".join((hook or "").split()).split(" ") if w]
    if not words:
        return "QUE BABADO?"
    words = words[:5]
    if len(words) < 3:
        words = (words + ["WEB", "DESCONFIA"])[:3]
    out = " ".join(words)
    if not out.endswith(("?", "!")):
        out += "?"
    return out.upper()


def _normalize_editorial_headline(headline: str) -> str:
    words = [w for w in " ".join((headline or "").split()).split(" ") if w]
    if not words:
        return "Web dividida"
    return " ".join(words[:4])


def _normalize_editorial_body(body: str, headline: str) -> str:
    seed = " ".join((body or "").split()).strip() or " ".join((headline or "").split()).strip()
    return _build_tarja_text(seed or "Revelacao chocante")


def _build_telegram_caption(*, hook: str, headline: str, cta: str, title: str, description: str, source_url: str) -> str:
    hook_line = " ".join((hook or "").split()).strip()
    headline_line = " ".join((headline or "").split()).strip()
    title_line = " ".join((title or "").split()).strip()
    desc_line = " ".join((description or "").split()).strip()
    cta_line = " ".join((cta or "").split()).strip()

    if not title_line:
        title_line = headline_line
    if not desc_line:
        desc_line = headline_line
    if len(desc_line) > 520:
        desc_line = desc_line[:520].rsplit(" ", 1)[0] + "..."
    if len(cta_line) > 64:
        cta_line = cta_line[:64].rsplit(" ", 1)[0] + "..."

    caption = (
        "🔥 BABADO RAPIDO\n\n"
        f"🧨 Hook: {hook_line or title_line}\n"
        f"📰 Titulo: {title_line}\n"
        f"📝 Resumo: {desc_line}\n"
        f"💬 CTA: {cta_line or 'COMENTA O QUE ACHOU!'}\n\n"
        f"🔗 Fonte: {source_url}"
    )
    if len(caption) > 1000:
        overflow = len(caption) - 1000
        if overflow > 0 and len(desc_line) > 80:
            desc_line = desc_line[:-overflow].rsplit(" ", 1)[0].strip()
            caption = (
                "🔥 BABADO RAPIDO\n\n"
                f"🧨 Hook: {hook_line or title_line}\n"
                f"📰 Titulo: {title_line}\n"
                f"📝 Resumo: {desc_line}\n"
                f"💬 CTA: {cta_line or 'COMENTA O QUE ACHOU!'}\n\n"
                f"🔗 Fonte: {source_url}"
            )
    return caption


def main():
    parser = argparse.ArgumentParser(
        description="Cria um post de fofoca com vídeo do Twitter/X",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Post básico
  python3 scripts/create_new_video_post.py \\
      --url "https://x.com/user/status/123" \\
      --hook "TRETA!!" \\
      --headline "FULANO E CICLANO BRIGAM NO BBB"

  # Post com mais opções
  python3 scripts/create_new_video_post.py \\
      --url "https://x.com/user/status/123" \\
      --hook "ELIMINADA!" \\
      --headline "PARTICIPANTE DEIXA O BBB APOS VOTACAO APERTADA" \\
      --cta "LIKE SE MERECIA" \\
      --duration 30 \\
      --name "eliminacao_bbb"
        """
    )
    
    parser.add_argument("--url", required=True, help="URL do vídeo no Twitter/X")
    parser.add_argument("--hook", required=True, help="Hook editorial (3-5 palavras)")
    parser.add_argument("--headline", required=True, help="Headline central (ate 4 palavras)")
    parser.add_argument("--body", default="", help="Body/tarja editorial (2-3 palavras)")
    parser.add_argument("--cta", default=None, help="Call-to-action (se não informado, será gerado automaticamente)")
    parser.add_argument("--duration", type=float, default=11.0, help="Duração máxima em segundos (padrao 11s)")
    parser.add_argument("--name", default="video_post", help="Nome do arquivo (sem extensão)")
    parser.add_argument("--skip-preview", action="store_true", help="Pula o preview do texto")
    parser.add_argument("--skip-telegram", action="store_true", help="Não envia para o Telegram")
    parser.add_argument("--telegram-title", default="", help="Título para caption do Telegram")
    parser.add_argument("--telegram-description", default="", help="Descrição para caption do Telegram")
    parser.add_argument(
        "--send-original",
        action="store_true",
        help="Após enviar o post, envia também o vídeo original na sequência",
    )
    
    args = parser.parse_args()
    args.hook = _normalize_editorial_hook(args.hook)
    args.headline = _normalize_editorial_headline(args.headline)
    args.body = _normalize_editorial_body(args.body, args.headline)
    if abs(args.duration - 11.0) > 0.001:
        print("ℹ️ Diretriz ativa: duração normalizada para 11s.")
    args.duration = 11.0

    # Se CTA não for fornecido, gera um baseado no headline
    cta = args.cta if args.cta else _get_random_cta(args.headline, args.headline)
    
    # Preview do texto
    if not args.skip_preview:
        text_ok = preview_text(args.headline)
        if not text_ok:
            resp = input("\n⚠️  Texto muito longo. Continuar mesmo assim? [s/N]: ")
            if resp.lower() not in ['s', 'sim', 'y', 'yes']:
                print("❌ Cancelado pelo usuário")
                return 1
    
    # Caminhos
    root = Path(__file__).resolve().parents[1]
    post_dir = root / "gossip_post"
    post_dir.mkdir(exist_ok=True)
    
    output_dir = post_dir / "output"
    output_dir.mkdir(exist_ok=True)
    
    video_raw = output_dir / f"{args.name}_raw.mp4"
    output_video = output_dir / f"{args.name}_post.mp4"
    
    # Baixar vídeo
    print("\n📥 Baixando vídeo do Twitter...")
    try:
        _download_video_with_fallback(args.url, video_raw)
        print(f"✅ Vídeo baixado: {video_raw}")
    except Exception as e:
        print(f"❌ Erro ao baixar vídeo: {e}")
        return 1
    
    # Criar arquivos de texto
    hook_file = post_dir / f"hook_{args.name}.txt"
    headline_file = post_dir / f"headline_{args.name}.txt"
    body_file = post_dir / f"summary_{args.name}.txt"
    
    hook_file.write_text(args.hook, encoding="utf-8")
    headline_file.write_text(args.headline, encoding="utf-8")
    body_file.write_text(args.body, encoding="utf-8")
    
    # Logo (se existir)
    logo_path = None
    for name in ("logo.png", "logo.webp", "logo.jpg", "logo.jpeg"):
        candidate = post_dir / name
        if candidate.exists():
            logo_path = candidate
            break
    if logo_path is None:
        candidate = root / "assets" / "Logo" / "logo.png"
        if candidate.exists():
            logo_path = candidate
    
    # Renderizar
    print("\n🎬 Renderizando post com overlay de texto...")
    try:
        _render_short_video(
            video_raw,
            headline_file,
            "GOSSIP",
            output_video,
            hook_file=hook_file,
            summary_file=body_file,
            cta_text=cta,
            logo_path=logo_path,
            duration_s=args.duration,
        )
    except Exception as e:
        print(f"❌ Erro ao renderizar: {e}")
        return 1
    
    print("\n" + "=" * 70)
    print(f"✅ Post '{args.name}' concluído!")
    print(f"📁 Vídeo: {output_video}")
    print("=" * 70)

    artifact = {
        "name": args.name,
        "source_url": args.url,
        "video_raw": str(video_raw.relative_to(root)),
        "video_output": str(output_video.relative_to(root)),
        "duration_s": args.duration,
        "hook": args.hook,
        "headline": args.headline,
        "body": args.body,
        "cta": cta,
    }
    artifact_path = output_video.with_suffix(".json")
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    
    # Enviar para Telegram
    if not args.skip_telegram:
        title = (args.telegram_title or args.headline).strip()
        description = (args.telegram_description or args.headline).strip()
        caption = _build_telegram_caption(
            hook=args.hook,
            headline=args.headline,
            cta=cta,
            title=title,
            description=description,
            source_url=args.url,
        )
        print("\n📱 Enviando para Telegram...")
        
        try:
            if _send_video_to_telegram(output_video, caption):
                print("✅ Vídeo enviado com sucesso!")
                if args.send_original:
                    print("\n📎 Enviando vídeo original na sequência...")
                    sent = _send_document_to_telegram(
                        video_raw,
                        f"📎 VÍDEO ORIGINAL\n\n🔗 Fonte: {args.url}",
                    )
                    if sent:
                        print("✅ Original enviado!")
                    else:
                        print("⚠️ Não foi possível enviar o original")
            else:
                print("⚠️ Erro ao enviar para Telegram")
        except Exception as e:
            print(f"⚠️ Erro ao enviar: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
