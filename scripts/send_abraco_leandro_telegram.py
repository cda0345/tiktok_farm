import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from create_gossip_post import _send_video_to_telegram

def main():
    video_path = Path("gossip_post/output/gossip_abraco_leandro_post.mp4")
    caption = "🤗 RECONCILIAÇÃO!\n\n💚 BROTHERS DÃO ABRAÇO EM LEANDRO APÓS DISCUSSÃO\n\n#BBB #BBB26 #Leandro #Reconciliacao #Abraco #Emocao"
    
    print(f"Enviando vídeo: {video_path}")
    print(f"Arquivo existe: {video_path.exists()}")
    if video_path.exists():
        print(f"Tamanho: {video_path.stat().st_size / (1024*1024):.2f} MB")
    
    result = _send_video_to_telegram(video_path, caption)
    print(f"Resultado: {'✅ Sucesso' if result else '❌ Falha'}")

if __name__ == "__main__":
    main()
