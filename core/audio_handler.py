from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np


@dataclass(frozen=True)
class BeatGrid:
    bpm: float
    beats: list[float]
    start_offset: float


_BPM_RE = re.compile(r"(?P<bpm>\d{2,3})\s*bpm", re.IGNORECASE)


def _bpm_from_track_id(track_id: str) -> float | None:
    m = _BPM_RE.search(track_id.replace("_", " "))
    if not m:
        return None
    try:
        bpm = float(m.group("bpm"))
        if 60.0 <= bpm <= 200.0:
            return bpm
    except Exception:
        return None
    return None


def analyze_beats(audio_path: str, target_sr: int = 22050) -> BeatGrid:
    p = Path(audio_path)
    if not p.exists():
        raise FileNotFoundError(f"Missing audio track: {audio_path}")

    y, sr = librosa.load(str(p), sr=target_sr, mono=True)

    # Trim leading silence to help "start on beat"
    yt, idx = librosa.effects.trim(y, top_db=30)
    offset_s = float(idx[0]) / float(sr)

    # Beat tracking
    bpm_hint = _bpm_from_track_id(p.stem)

    onset_env = librosa.onset.onset_strength(y=yt, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, start_bpm=bpm_hint or 128.0)

    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    beat_times = beat_times.tolist()

    # Choose start offset at first detected beat (after trimmed offset)
    if beat_times:
        start_offset = offset_s + float(beat_times[0])
    else:
        start_offset = offset_s

    return BeatGrid(
        bpm=float(tempo),
        beats=[offset_s + float(t) for t in beat_times],
        start_offset=float(start_offset),
    )


def beat_period_s(bpm: float) -> float:
    bpm = max(1e-6, float(bpm))
    return 60.0 / bpm


def choose_cut_durations(max_duration_s: float, bpm: float, clip_min_s: float, clip_max_s: float, rng: np.random.Generator) -> list[float]:
    period = beat_period_s(bpm)

    durations: list[float] = []
    total = 0.0
    
    # Safety: max iterations to prevent infinite loop
    max_iterations = 1000
    iteration = 0
    
    # We want to vary the "intensity" in rhythmic sections (phrases)
    while total < max_duration_s - 0.1 and iteration < max_iterations:
        iteration += 1
        
        # Each phrase lasts about 4-8 beats
        phrase_rhythm = rng.choice(['normal', 'fast', 'slow', 'mixed'])
        phrase_beats_target = rng.integers(4, 9)
        phrase_beats_acc = 0.0
        
        inner_iteration = 0
        while phrase_beats_acc < phrase_beats_target and inner_iteration < 20:
            inner_iteration += 1
            
            if phrase_rhythm == 'normal':
                m = 1.0
            elif phrase_rhythm == 'fast':
                m = 0.5
            elif phrase_rhythm == 'slow':
                m = 2.0
            else: # mixed
                m = rng.choice([0.5, 1.0, 2.0])
            
            # Occasionally allow ultra-fast cuts if in fast/mixed mode
            if phrase_rhythm in ['fast', 'mixed'] and rng.random() < 0.15:
                m = 0.25

            dur = m * period
            
            # Respect absolute minimum duration for visual clarity (usually 0.2s)
            if dur < 0.18:
                # If we really want a 0.25 beat cut, it must be at high BPM
                # Otherwise, fallback to 0.5
                if m == 0.25:
                    m = 0.5
                    dur = m * period

            if total + dur > max_duration_s + 0.05:
                break
                
            durations.append(dur)
            total += dur
            phrase_beats_acc += m
        
        if total >= max_duration_s - 0.1:
            break
    
    # Ensure we have at least some durations
    if not durations:
        # Fallback: simple 1-beat cuts
        while total < max_duration_s - 0.05:
            durations.append(period)
            total += period
            
    return durations
