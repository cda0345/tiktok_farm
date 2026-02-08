"""
Extract b-roll video IDs from terminal output to identify which clips were used.
Run this to analyze the batch_regenerate_variants.py output.
"""
import re
from collections import Counter

# Paste the terminal output here
TERMINAL_OUTPUT = """
[Paste terminal output from batch_regenerate_variants.py here]
"""

def extract_brolls(text: str) -> dict[str, list[str]]:
    """Extract b-roll video IDs used in each post."""
    results = {}
    current_post = None
    current_variant = None
    
    # Pattern for post processing: [1/30] Processing: post_001_peggy_gou_nanana
    post_pattern = r'\[\d+/\d+\] Processing: (post_\d+_.*?)$'
    # Pattern for variant: Rendering v1 -> v1.mp4
    variant_pattern = r'Rendering (v\d+) -> v\d+\.mp4'
    # Pattern for segment: Segment 1/22: yt_kNZQFbCeWcQ.mp4 (0.23s)... ✅
    segment_pattern = r'Segment \d+/\d+: (yt_[a-zA-Z0-9_-]+)\.mp4'
    
    for line in text.split('\n'):
        # Check if new post
        post_match = re.search(post_pattern, line)
        if post_match:
            current_post = post_match.group(1).strip()
            if current_post not in results:
                results[current_post] = {'v1': [], 'v2': [], 'v3': []}
            continue
        
        # Check if new variant
        variant_match = re.search(variant_pattern, line)
        if variant_match and current_post:
            current_variant = variant_match.group(1)
            continue
        
        # Check if segment
        segment_match = re.search(segment_pattern, line)
        if segment_match and current_post and current_variant:
            video_id = segment_match.group(1)
            results[current_post][current_variant].append(video_id)
    
    return results


def find_problematic_clips(brolls_data: dict) -> Counter:
    """Count frequency of each clip across all posts/variants to identify overused or problematic ones."""
    all_clips = []
    for post, variants in brolls_data.items():
        for variant, clips in variants.items():
            all_clips.extend(clips)
    
    return Counter(all_clips)


def print_report(brolls_data: dict):
    """Print detailed report of b-rolls used."""
    print("=" * 80)
    print("B-ROLL USAGE REPORT")
    print("=" * 80)
    
    for post, variants in brolls_data.items():
        print(f"\n{post}:")
        for variant, clips in variants.items():
            if clips:
                unique_clips = len(set(clips))
                total_clips = len(clips)
                print(f"  {variant}: {total_clips} segments, {unique_clips} unique clips")
                # Show unique clips used
                for clip in sorted(set(clips)):
                    count = clips.count(clip)
                    print(f"    - {clip}.mp4 (used {count}x)")
    
    # Overall statistics
    print("\n" + "=" * 80)
    print("CLIP FREQUENCY (across all posts/variants)")
    print("=" * 80)
    
    clip_counter = find_problematic_clips(brolls_data)
    
    # Sort by frequency (most used first)
    for clip_id, count in clip_counter.most_common():
        print(f"  {clip_id}.mp4: {count} uses")
    
    print("\n" + "=" * 80)
    print(f"Total unique clips used: {len(clip_counter)}")
    print("=" * 80)


if __name__ == "__main__":
    # Extract data
    data = extract_brolls(TERMINAL_OUTPUT)
    
    if not data:
        print("No b-roll data found. Please paste the terminal output in the TERMINAL_OUTPUT variable.")
    else:
        print_report(data)
        
        # Identify potentially problematic clips (used very frequently)
        clip_counter = find_problematic_clips(data)
        most_common = clip_counter.most_common(10)
        
        print("\n" + "=" * 80)
        print("TOP 10 MOST USED CLIPS (potential blacklist candidates)")
        print("=" * 80)
        for clip_id, count in most_common:
            print(f"  {clip_id}.mp4 - {count} uses")
        
        print("\nReview these clips manually. If any look bad, add to blacklist in providers/youtube.py")
