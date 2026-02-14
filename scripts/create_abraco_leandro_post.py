from pathlib import Path
import sys
import subprocess

# Adiciona o diretório scripts ao path
sys.path.insert(0, str(Path(__file__).parent))
from create_gossip_post import _render_short_video, ensure_ffmpeg

def main():
    # Caminhos
    root = Path(__file__).resolve().parents[1]
    post_dir = root / "gossip_post"
    video_full = post_dir / "output" / "gossip_abraco_leandro_bbb_full.mp4"
    video_cut = post_dir / "output" / "gossip_abraco_leandro_bbb_15s.mp4"
    output_video = post_dir / "output" / "gossip_abraco_leandro_post.mp4"

    # Obtém a duração total do vídeo
    ff = ensure_ffmpeg("tools")
    probe_cmd = [
        str(ff.ffprobe),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_full)
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    duration_total = float(result.stdout.strip())
    
    # Calcula o ponto de início para pegar os últimos 15 segundos
    start_time = max(0, duration_total - 15)
    
    print(f"Duração total: {duration_total:.2f}s")
    print(f"Cortando dos últimos 15s: {start_time:.2f}s até {duration_total:.2f}s")
    
    # Corta os últimos 15 segundos do vídeo
    cut_cmd = [
        str(ff.ffmpeg),
        "-hide_banner",
        "-y",
        "-ss", str(start_time),
        "-i", str(video_full),
        "-t", "15",
        "-c", "copy",
        str(video_cut)
    ]
    subprocess.run(cut_cmd, check=True)
    print(f"✅ Vídeo cortado: {video_cut}")

    # Textos do post
    hook_text = "RECONCILIACAO!"
    headline_text = "BROTHERS DAO ABRACO EM LEANDRO APOS DISCUSSAO"

    # Cria arquivos temporários com os textos
    hook_file = post_dir / "hook_abraco.txt"
    headline_file = post_dir / "headline_abraco.txt"
    
    hook_file.write_text(hook_text, encoding="utf-8")
    headline_file.write_text(headline_text, encoding="utf-8")

    # Logo (se existir)
    logo_path = None
    for name in ("logo.png", "logo.webp", "logo.jpg", "logo.jpeg"):
        candidate = post_dir / name
        if candidate.exists():
            logo_path = candidate
            break

    # Renderiza usando a função padrão do gossip, mas com vídeo cortado
    _render_short_video(
        video_cut,
        headline_file,
        "BBB",
        output_video,
        hook_file=hook_file,
        summary_file=headline_file,
        cta_text="CURTE SE FOI LINDO",
        logo_path=logo_path,
    )

    print("=" * 64)
    print(f"✅ Post Abraço Leandro concluído!")
    print(f"Vídeo: {output_video}")
    print("=" * 64)

if __name__ == "__main__":
    main()
