from pathlib import Path
import sys

# Adiciona o diretório scripts ao path para importar funções do create_gossip_post
sys.path.insert(0, str(Path(__file__).parent))
from create_gossip_post import _render_short_video

def main():
    # Caminhos
    root = Path(__file__).resolve().parents[1]
    post_dir = root / "gossip_post"
    video_input = post_dir / "output" / "gossip_leandro_chora_bbb.mp4"
    output_video = post_dir / "output" / "gossip_leandro_chora_post.mp4"

    # Textos
    hook_text = "CHORO NO BBB!"
    headline_text = "LEANDRO CHORA APOS BRIGA COM EDILSON"

    # Cria arquivos temporários com os textos
    hook_file = post_dir / "hook_leandro.txt"
    headline_file = post_dir / "headline_leandro.txt"
    
    hook_file.write_text(hook_text, encoding="utf-8")
    headline_file.write_text(headline_text, encoding="utf-8")

    # Logo (se existir)
    logo_path = None
    for name in ("logo.png", "logo.webp", "logo.jpg", "logo.jpeg"):
        candidate = post_dir / name
        if candidate.exists():
            logo_path = candidate
            break

    # Renderiza usando a função padrão do gossip, mas com vídeo
    _render_short_video(
        video_input,
        headline_file,
        "BBB",
        output_video,
        hook_file=hook_file,
        summary_file=headline_file,
        cta_text="CURTE SE FICOU COM PENA",
        logo_path=logo_path,
    )

    print("=" * 64)
    print(f"✅ Post Leandro Chora concluído!")
    print(f"Vídeo: {output_video}")
    print("=" * 64)

if __name__ == "__main__":
    main()
