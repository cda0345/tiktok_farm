import re
from pathlib import Path

def parse_lrc(file_path: str | Path):
    """
    Parses an LRC file into a list of (start_time, text).
    """
    path = Path(file_path)
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    events = []
    
    # Pattern for [mm:ss.xx] or [mm:ss:xx] or [mm:ss]
    pattern = re.compile(r"\[(\d+):(\d+)(?:\.|:)(\d+)\](.*)")
    # Pattern for [mm:ss] without ms
    pattern_simple = re.compile(r"\[(\d+):(\d+)\](.*)")

    for line in lines:
        match = pattern.match(line)
        if match:
            m, s, ms, text = match.groups()
            start_time = int(m) * 60 + int(s) + int(ms) / 100.0
            events.append({"start": start_time, "text": text.strip()})
        else:
            match = pattern_simple.match(line)
            if match:
                m, s, text = match.groups()
                start_time = int(m) * 60 + int(s)
                events.append({"start": start_time, "text": text.strip()})
    
    # Resolve end times (duration of each line)
    resolved = []
    for i in range(len(events)):
        start = events[i]["start"]
        text = events[i]["text"]
        
        if not text:
            continue
            
        # End time is the next event start or +4 seconds
        if i + 1 < len(events):
            end = events[i+1]["start"]
        else:
            end = start + 4.0
            
        # Cap duration to avoid very long lines
        if end - start > 5.0:
            end = start + 5.0
            
        resolved.append((start, end, text))
        
    return resolved

def find_lyrics_segment(events: list[tuple[float, float, str]], target_duration: float = 10.0, start_offset: float | None = None):
    """
    Finds a window of lyrics of target_duration.
    If start_offset is provided, starts there.
    Otherwise, looks for a segment with high text density (simple chorus heuristic).
    """
    if not events:
        return 0.0, []

    if start_offset is not None:
        win_start = start_offset
    else:
        # Simple heuristic: find where lyrics are most "packed" 
        # For home-made TikToks, starting at 1/3 of the song is usually a safe bet for chorus
        # Or just find the first lyric.
        win_start = events[0][0]
        # Let's try to find a repeating sequence if possible (chorus)
        # For now, just taking the first 10 seconds of lyrics is easier for the user to adjust
        pass

    win_end = win_start + target_duration
    
    # Filter and shift events to be relative to win_start
    result = []
    for s, e, t in events:
        # Overlap with [win_start, win_end]
        o_start = max(win_start, s)
        o_end = min(win_end, e)
        
        if o_start < o_end:
            result.append((o_start - win_start, o_end - win_start, t))
            
    return win_start, result
