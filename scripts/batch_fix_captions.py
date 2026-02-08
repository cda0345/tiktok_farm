import os
from pathlib import Path
from core.ai_client import OpenAIConfig, generate_caption_and_hashtags, generate_final_caption, is_openai_configured
from dotenv import load_dotenv

def fix_captions():
    load_dotenv()
    cfg = OpenAIConfig()
    
    if not is_openai_configured(cfg):
        print("Error: OpenAI not configured. Check .env")
        return

    posts_dir = Path("d:/projeto_insta_pc/posts")
    post_folders = sorted([d for d in posts_dir.iterdir() if d.is_dir() and d.name.startswith("post_2")])
    
    print(f"Found {len(post_folders)} posts in 200 series.")
    
    for post in post_folders:
        cap_file = post / "caption.txt"
        spec_file = post / "caption_spec.txt"
        
        if not cap_file.exists():
            continue
            
        content = cap_file.read_text(encoding="utf-8")
        if "Midnight city flow" in content:
            print(f"Fixing caption for {post.name}...")
            
            # Extract themes from spec if possible
            themes = ["vintage", "retro", "90s", "tennis"] # Fallback for this batch
            if spec_file.exists():
                spec_lines = spec_file.read_text(encoding="utf-8").splitlines()
                for line in spec_lines:
                    if line.startswith("themes="):
                        themes = line.split("=")[1].split(",")
            
            track_id = post.name.replace("post_", "", 1)
            
            # Generate new ones
            try:
                line1, tags = generate_caption_and_hashtags(
                    themes=themes,
                    niche="HOUSE MUSIC + LIFESTYLE / NIGHTLIFE / LUXURY",
                    cfg=cfg
                )
                final = generate_final_caption(
                    themes=themes,
                    niche="HOUSE MUSIC + LIFESTYLE / NIGHTLIFE / LUXURY",
                    track_id=track_id,
                    cfg=cfg
                )
                
                # Update files
                cap_file.write_text(final.strip() + "\n", encoding="utf-8")
                spec_file.write_text(
                    "\n".join([line1, tags, f"track_id={track_id}", f"themes={','.join(themes)}"]) + "\n",
                    encoding="utf-8"
                )
                print(f"  Done: {line1}")
            except Exception as e:
                print(f"  Error fixing {post.name}: {e}")

if __name__ == "__main__":
    fix_captions()
