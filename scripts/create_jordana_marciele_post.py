from pathlib import Path
import sys
import subprocess

# Adiciona o diretório scripts ao path para importar funções do create_gossip_post
sys.path.insert(0, str(Path(__file__).parent))
from create_gossip_post import _render_short_video, _send_video_to_telegram

def main():
    # Caminhos
    root = Path(__file__).resolve().parents[1]
    post_dir = root / "gossip_post"
    post_dir.mkdir(exist_ok=True)
    
    output_dir = post_dir / "output"
    output_dir.mkdir(exist_ok=True)
    
    video_raw = output_dir / "jordana_marciele_raw.mp4"
    output_video = output_dir / "jordana_marciele_post.mp4"

    # Baixar vídeo do Twitter/X
    print("📥 Baixando vídeo do Twitter...")
    url = "https://x.com/krlasrt/status/2022937595622174905"
    subprocess.run([
        "yt-dlp",
        "-f", "mp4",
        "-o", str(video_raw),
        url
    ], check=True)
    
    print(f"✅ Vídeo baixado: {video_raw}")

    # Textos (versão mais longa para testar o fix)
    hook_text = "QUASE SE BEIJARAM?!"
    headline_text = "JORDANA E MARCIELE TROCAM PROVOCACOES E CLIMA ESQUENTA NA FESTA DO BBB VOCE ACHA QUE ELAS ESTAO SE APROXIMANDO"

    # Cria arquivos temporários com os textos
    hook_file = post_dir / "hook_jordana_marciele.txt"
    headline_file = post_dir / "headline_jordana_marciele.txt"
    
    hook_file.write_text(hook_text, encoding="utf-8")
    headline_file.write_text(headline_text, encoding="utf-8")

    # Logo (se existir)
    logo_path = None
    for name in ("logo.png", "logo.webp", "logo.jpg", "logo.jpeg"):
        candidate = post_dir / name
        if candidate.exists():
            logo_path = candidate
            break

    print("🎬 Renderizando post com overlay de texto...")
    
    # Renderiza usando a função padrão do gossip, com vídeo completo (~35s)
    _render_short_video(
        video_raw,
        headline_file,
        "BBB",
        output_video,
        hook_file=hook_file,
        summary_file=headline_file,
        cta_text="CURTE SE FICOU CHOCADO",
        logo_path=logo_path,
        duration_s=40.0,  # Permite até 40s para manter o vídeo completo
    )

    print("=" * 64)
    print(f"✅ Post Jordana & Marciele concluído!")
    print(f"Vídeo final: {output_video}")
    print("=" * 64)
    
    # Enviar para Telegram
    caption = "🔥 JORDANA E MARCIELE QUASE SE BEIJARAM?\n\nNa festa, as duas trocaram provocações, clima esquentou e a aproximação chamou atenção de quem estava por perto.\n\n#BBB #BBB26 #JordanaBartholdy #Marciele #Fofoca"
    
    print("\n📱 Enviando para Telegram...")
    if _send_video_to_telegram(output_video, caption):
        print("✅ Vídeo enviado para Telegram com sucesso!")
    else:
        print("⚠️ Erro ao enviar para Telegram. Verifique as configurações.")

if __name__ == "__main__":
    main()
