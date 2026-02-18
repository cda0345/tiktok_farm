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
import sys
from pathlib import Path
import subprocess
import textwrap

# Adiciona o diretório scripts ao path
sys.path.insert(0, str(Path(__file__).parent))
from create_gossip_post import _render_short_video, _send_video_to_telegram


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
    parser.add_argument("--hook", required=True, help="Texto do hook (ex: 'TRETA!!')")
    parser.add_argument("--headline", required=True, help="Texto principal da notícia")
    parser.add_argument("--cta", default="CURTE SE FICOU CHOCADO", help="Call-to-action")
    parser.add_argument("--duration", type=float, default=40.0, help="Duração máxima em segundos")
    parser.add_argument("--name", default="video_post", help="Nome do arquivo (sem extensão)")
    parser.add_argument("--skip-preview", action="store_true", help="Pula o preview do texto")
    parser.add_argument("--skip-telegram", action="store_true", help="Não envia para o Telegram")
    parser.add_argument("--telegram-title", default="", help="Título para caption do Telegram")
    parser.add_argument("--telegram-description", default="", help="Descrição para caption do Telegram")
    
    args = parser.parse_args()
    
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
        subprocess.run([
            "yt-dlp",
            "-f", "mp4",
            "-o", str(video_raw),
            args.url
        ], check=True)
        print(f"✅ Vídeo baixado: {video_raw}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao baixar vídeo: {e}")
        return 1
    
    # Criar arquivos de texto
    hook_file = post_dir / f"hook_{args.name}.txt"
    headline_file = post_dir / f"headline_{args.name}.txt"
    
    hook_file.write_text(args.hook, encoding="utf-8")
    headline_file.write_text(args.headline, encoding="utf-8")
    
    # Logo (se existir)
    logo_path = None
    for name in ("logo.png", "logo.webp", "logo.jpg", "logo.jpeg"):
        candidate = post_dir / name
        if candidate.exists():
            logo_path = candidate
            break
    
    # Renderizar
    print("\n🎬 Renderizando post com overlay de texto...")
    try:
        _render_short_video(
            video_raw,
            headline_file,
            "GOSSIP",
            output_video,
            hook_file=hook_file,
            summary_file=headline_file,
            cta_text=args.cta,
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
    
    # Enviar para Telegram
    if not args.skip_telegram:
        title = (args.telegram_title or args.headline).strip()
        description = (args.telegram_description or args.headline).strip()
        if len(description) > 700:
            description = description[:700].rsplit(" ", 1)[0] + "..."
        caption = (
            f"🎬 Título: {title}\n"
            f"📝 Descrição: {description}\n\n"
            f"🔗 Fonte: {args.url}"
        )
        print("\n📱 Enviando para Telegram...")
        
        try:
            if _send_video_to_telegram(output_video, caption):
                print("✅ Vídeo enviado com sucesso!")
            else:
                print("⚠️ Erro ao enviar para Telegram")
        except Exception as e:
            print(f"⚠️ Erro ao enviar: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
