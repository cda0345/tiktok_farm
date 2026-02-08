"""Analyze b-roll usage from completed batch generation."""
import re
from collections import Counter
from pathlib import Path

# Load the terminal output from get_terminal_output
terminal_output_file = Path(__file__).parent / "terminal_output.txt"

def extract_clips_from_line(line: str) -> str | None:
    """Extract video ID from segment line."""
    match = re.search(r'Segment \d+/\d+: (yt_[a-zA-Z0-9_-]+)\.mp4', line)
    return match.group(1) if match else None

def analyze_terminal_output(output: str) -> dict:
    """Parse terminal output and extract all used clips."""
    lines = output.split('\n')
    
    all_clips = []
    posts_data = {}
    current_post = None
    current_variant = None
    
    for line in lines:
        # Detect new post
        post_match = re.search(r'\[(\d+)/\d+\] Processing: (post_\d+_.*?)$', line)
        if post_match:
            current_post = post_match.group(2).strip()
            posts_data[current_post] = {'v1': [], 'v2': [], 'v3': []}
            continue
        
        # Detect variant
        variant_match = re.search(r'Rendering (v\d+) ->', line)
        if variant_match:
            current_variant = variant_match.group(1)
            continue
        
        # Extract clip from segment line
        clip = extract_clips_from_line(line)
        if clip and current_post and current_variant:
            all_clips.append(clip)
            posts_data[current_post][current_variant].append(clip)
    
    return all_clips, posts_data

# From terminal output
TERMINAL = """[30/30] Processing: post_030_purple_disco_machine_substitution
  Deleting old v2.mp4...
  Deleting old v3.mp4...
  Generating v1, v2, v3...

=== Processing post: post_030_purple_disco_machine_substitution ===
Audio: purple_disco_machine_substitution.mp3
Beat analysis: bpm=123.0 start_offset=2.30s
Loading b-roll themes: city_drive
🔍 Checking/Indexing 15 clips for themes ['city_drive']...
  ... 10/15 clips verified
B-roll clips found: 15
Rendering v1 -> v1.mp4
  Building edit plan (seed=941522752)...
  Plan ready: 17 segments, 9.00s total
🎬 Starting Engine: FAST 2-PASS
============================================================
🚀 USING FAST 2-PASS EXPORTER (exporter_fast.py)
============================================================
[Pass 1/2] Rendering 17 segments...
  Segment 1/17: yt_eqlQP9uOXl4.mp4 (0.24s)... ✅
  Segment 2/17: yt_4w8oGyrNsVg.mp4 (0.49s)... ✅
  Segment 3/17: yt_jMZGmWHDbqE.mp4 (0.24s)... ✅
  Segment 4/17: yt_HlJCMMCpQS4.mp4 (0.24s)... ✅
  Segment 5/17: yt_0Jb-5a3UWg0.mp4 (0.24s)... ✅
  Segment 6/17: yt_hrotHC9OPr4.mp4 (0.49s)... ✅
  Segment 7/17: yt_--HNKClBIz8.mp4 (0.24s)... ✅
  Segment 8/17: yt_VWM02zJLYvY.mp4 (0.98s)... ✅
  Segment 9/17: yt_nDjjfaAN2hQ.mp4 (0.98s)... ✅
  Segment 10/17: yt_jum8PGur1PU.mp4 (0.98s)... ✅
  Segment 11/17: yt_7_duz3-H2YI.mp4 (0.98s)... ✅
  Segment 12/17: yt_4nio5i0lLBM.mp4 (0.49s)... ✅
  Segment 13/17: yt_GFiBfbmBw-M.mp4 (0.49s)... ✅
  Segment 14/17: yt_YUAPn27ZlNs.mp4 (0.49s)... ✅
  Segment 15/17: yt_sD4VSdhEj0c.mp4 (0.49s)... ✅
  Segment 16/17: yt_VWM02zJLYvY.mp4 (0.49s)... ✅
  Segment 17/17: yt_eqlQP9uOXl4.mp4 (0.47s)... ✅"""

all_clips, posts_data = analyze_terminal_output(TERMINAL)

# Count frequency
clip_counter = Counter(all_clips)

print("=" * 80)
print("CLIP USAGE ANALYSIS - Post 030")
print("=" * 80)

for clip_id, count in clip_counter.most_common():
    print(f"  {clip_id}.mp4: {count} uses")

print("\nNOTE: Run this on the FULL terminal output to see all posts.")
print("You can copy the full output from the terminal and paste it into the TERMINAL variable.")
