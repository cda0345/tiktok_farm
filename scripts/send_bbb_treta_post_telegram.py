import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from create_gossip_post import _send_video_to_telegram

def main():
    video_path = Path("gossip_post/output/gossip_bbb_treta_post.mp4")
    caption = "Treta!!\n\nBoneco e Edilson brigam no BBB"
    _send_video_to_telegram(video_path, caption)

if __name__ == "__main__":
    main()
