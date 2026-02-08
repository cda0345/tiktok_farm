#!/usr/bin/env python3
"""Download more b-roll videos for specific categories."""

import sys
from pathlib import Path
from providers.youtube import YouTubeVideoProvider

# Multiple queries for each category (will try all until target is reached)
CATEGORY_QUERIES = {
    "city_drive": ["night drive city pov lights"],
    "luxury_bar": [
        "nightclub vip lounge atmosphere",
        "luxury nightclub interior lights",
        "elegant bar nightlife ambience",
        "premium club lounge vibe",
        "afterhours nightclub atmosphere",
        "upscale nightclub interior",
        "sophisticated bar atmosphere night"
    ],
    "vintage_retro": [
        "vintage tennis match 16mm film",
        "90s nyc street style vhs",
        "retro sports aesthetic 90s tennis",
        "old school house dance floor vhs",
        "vintage record store aesthetic",
        "retro lifestyle film grain",
        "90s arcade aesthetic neon night",
        "Roger Federer best points slow motion",
        "Rafael Nadal intense rally 4k",
        "Novak Djokovic legendary defense cinematic",
        "Carlos Alcaraz powerful forehand slow motion",
        "Jannik Sinner high speed rally cinematic"
    ]
}

def download_more(category: str, count: int):
    """Download more videos for a category."""
    queries = CATEGORY_QUERIES.get(category)
    if not queries:
        print(f"Error: Unknown category '{category}'")
        return
    
    dest_dir = Path("broll_library") / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print(f"📥 Downloading {count} more videos for category: {category}")
    print(f"Destination: {dest_dir}")
    print(f"{'='*80}\n")
    
    provider = YouTubeVideoProvider()
    
    # Get current count
    existing = list(dest_dir.glob("*.mp4"))
    current_count = len(existing)
    target_count = current_count + count
    
    print(f"Current videos: {current_count}")
    print(f"Target: {target_count}\n")
    
    # Try each query until we reach target
    for query in queries:
        current_videos = len(list(dest_dir.glob("*.mp4")))
        if current_videos >= target_count:
            break
            
        remaining = target_count - current_videos
        print(f"\n🔍 Trying query: '{query}' (need {remaining} more)")
        
        try:
            videos = provider.ensure_videos(
                query=query,
                dest_dir=str(dest_dir),
                min_count=target_count
            )
        except Exception as e:
            print(f"⚠️  Query failed: {e}")
            continue
    
    new_count = len(list(dest_dir.glob("*.mp4")))
    downloaded = new_count - current_count
    
    print(f"\n✅ Complete!")
    print(f"Downloaded: {downloaded} new videos")
    print(f"Total in {category}: {new_count}")
    1
    if new_count < target_count:
        print(f"⚠️  Warning: Only reached {new_count}/{target_count} videos")

if __name__ == "__main__":
    download_more("vintage_retro", 20)
