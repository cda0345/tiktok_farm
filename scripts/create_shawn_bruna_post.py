from pathlib import Path
import sys
import subprocess

# Adiciona o diretório scripts ao path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Importa as funções necessárias do create_gossip_post
# Como ele está no mesmo diretório, podemos importar diretamente
sys.path.insert(0, str(Path(__file__).parent))
from create_gossip_post import _render_short_video, ensure_ffmpeg

def main():
    print("Iniciando script...")
    # Caminhos
    root = Path(__file__).resolve().parents[1]
    gossip_dir = root / "gossip_post"
    br_dir = root / "gossip_posts_br"
    
    # Arquivo de vídeo baixado
    video_raw = br_dir / "shawn_bruna_carnaval_raw.mp4"
    output_video = br_dir / "post_shawn_bruna_carnaval.mp4"

    if not video_raw.exists():
        print(f"Erro: Vídeo não encontrado em {video_raw}")
        return

    print(f"Vídeo de origem encontrado: {video_raw}")

    # Textos do post
    hook_text = "" # Removido conforme solicitado para não obstruir o vídeo vertical
    headline_text = "BRUNA MARQUEZINE E SHAWN MENDES CURTEM CARNAVAL JUNTOS"

    # Cria arquivos temporários com os textos
    hook_file = br_dir / "hook_shawn_bruna.txt"
    headline_file = br_dir / "headline_shawn_bruna.txt"
    summary_file = br_dir / "summary_shawn_bruna.txt"
    
    hook_file.write_text(hook_text, encoding="utf-8")
    headline_file.write_text(headline_text, encoding="utf-8")
    summary_file.write_text(headline_text, encoding="utf-8") # Usa o mesmo para summary se necessário

    # Logo (se existir no diretório gossip_post)
    logo_path = None
    for name in ("logo.png", "logo.webp", "logo.jpg", "logo.jpeg"):
        candidate = gossip_dir / name
        if candidate.exists():
            logo_path = candidate
            break

    print(f"🎬 Renderizando vídeo para: {output_video}")
    
    try:
        # Renderiza usando a função padrão do gossip
        _render_short_video(
            video_raw,
            headline_file,
            "CARNAVAL",
            output_video,
            hook_file=hook_file,
            summary_file=summary_file,
            cta_text="SEGUE PRA MAIS BABADO",
            logo_path=logo_path,
        )
        print("Chamada para _render_short_video concluída.")
    except Exception as e:
        print(f"Erro durante a renderização: {e}")

    if output_video.exists():
        print("=" * 64)
        print(f"✅ Post Bruna e Shawn concluído!")
        print(f"Vídeo: {output_video}")
        print("=" * 64)
    else:
        print("❌ FALHA: O vídeo de saída não foi gerado.")

if __name__ == "__main__":
    main()
