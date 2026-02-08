"""Regenerate v2 and v3 for all posts."""
from pathlib import Path
import subprocess
import sys

def get_all_posts(posts_dir: Path) -> list[Path]:
    """Get all post directories."""
    if not posts_dir.exists():
        return []
    
    posts = []
    for p in sorted(posts_dir.iterdir()):
        if p.is_dir() and (p / "caption_spec.txt").exists():
            posts.append(p)
    return posts

def main():
    posts_dir = Path("posts")
    posts = get_all_posts(posts_dir)
    
    if not posts:
        print("No posts found!")
        return 1
    
    print(f"Found {len(posts)} posts")
    print("=" * 80)
    
    success = []
    failed = []
    
    for i, post_dir in enumerate(posts, 1):
        post_name = post_dir.name
        print(f"\n[{i}/{len(posts)}] Processing: {post_name}")
        
        # Delete v2 and v3 if they exist
        output_dir = post_dir / "output"
        if output_dir.exists():
            for variant in ["v2.mp4", "v3.mp4"]:
                variant_path = output_dir / variant
                if variant_path.exists():
                    print(f"  Deleting old {variant}...")
                    variant_path.unlink()
        
        # Run generation
        cmd = [
            sys.executable,
            "main.py",
            "--broll-dir", "broll_library",
            "--only", post_name,
            "--overwrite"
        ]
        
        print(f"  Generating v1, v2, v3...")
        try:
            result = subprocess.run(cmd, check=True, capture_output=False)
            if result.returncode == 0:
                success.append(post_name)
                print(f"  ✅ Success!")
            else:
                failed.append(post_name)
                print(f"  ❌ Failed with code {result.returncode}")
        except subprocess.CalledProcessError as e:
            failed.append(post_name)
            print(f"  ❌ Failed: {e}")
        except Exception as e:
            failed.append(post_name)
            print(f"  ❌ Error: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Success: {len(success)}/{len(posts)}")
    print(f"❌ Failed: {len(failed)}/{len(posts)}")
    
    if failed:
        print("\nFailed posts:")
        for post in failed:
            print(f"  - {post}")
    
    return 0 if not failed else 1

if __name__ == "__main__":
    sys.exit(main())
