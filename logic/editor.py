from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.audio_handler import BeatGrid, choose_cut_durations
from logic.broll_loader import ClipMeta
from core.config import RenderConfig


@dataclass(frozen=True)
class Segment:
    src: str
    in_start: float
    in_dur: float
    out_dur: float
    speed: float
    motion: float


@dataclass(frozen=True)
class EditPlan:
    segments: list[Segment]
    duration: float
    used_videos: list[str] = None  # List of video paths used in the edit


def build_edit_plan(
    metas: list[ClipMeta],
    beat: BeatGrid,
    cfg: RenderConfig,
    seed: int,
    loop: bool = True,
) -> EditPlan:
    rng = np.random.default_rng(seed)

    # Prioritize durations based on config range
    min_dur = getattr(cfg, "min_duration_s", 5.0)
    target_dur = float(rng.uniform(min_dur, cfg.max_duration_s))
    
    durations = choose_cut_durations(
        max_duration_s=target_dur,
        bpm=beat.bpm,
        clip_min_s=cfg.clip_min_s,
        clip_max_s=cfg.clip_max_s,
        rng=rng,
    )

    n = len(durations)
    if n <= 0:
        raise RuntimeError("No durations generated")

    # Prefer higher motion in second half ("drop")
    sorted_by_motion = sorted(metas, key=lambda m: m.motion, reverse=True)
    high_motion_pool = sorted_by_motion[: max(6, min(len(sorted_by_motion), 24))]
    low_motion_pool = sorted_by_motion[max(0, len(sorted_by_motion) // 3) :]
    if not low_motion_pool:
        low_motion_pool = metas

    used: set[str] = set()
    segments: list[Segment | None] = [None] * n

    # Infinite loop illusion logic
    loop_meta = None
    if loop and n >= 2:
        loop_meta = rng.choice(high_motion_pool if high_motion_pool else metas)
        loop_speed = float(rng.uniform(cfg.speed_min, cfg.speed_max))
        
        first_in_dur = durations[0] * loop_speed
        last_in_dur = durations[-1] * loop_speed
        total_in_dur = first_in_dur + last_in_dur
        
        margin = 0.1
        latest = max(0.0, loop_meta.duration - total_in_dur - margin)
        loop_in_start = float(rng.uniform(0.0, latest)) if latest > 0.1 else 0.0
        
        # First segment (Segment 0) starts AFTER the part used in Last segment (Segment n-1)
        # So when it loops: Last -> First is seamless
        segments[0] = Segment(
            src=loop_meta.path,
            in_start=loop_in_start + last_in_dur,
            in_dur=first_in_dur,
            out_dur=durations[0],
            speed=loop_speed,
            motion=float(loop_meta.motion)
        )
        
        segments[-1] = Segment(
            src=loop_meta.path,
            in_start=loop_in_start,
            in_dur=last_in_dur,
            out_dur=durations[-1],
            speed=loop_speed,
            motion=float(loop_meta.motion)
        )
        used.add(loop_meta.path)

    last_src: str | None = loop_meta.path if loop_meta else None

    for i in range(n):
        if segments[i] is not None:
            continue
            
        out_dur = durations[i]
        in_drop = i >= int(0.55 * n)
        pool = high_motion_pool if in_drop else low_motion_pool

        # Choose an unused clip first; avoid consecutive repeats.
        choices = [m for m in pool if m.path not in used]
        if not choices:
            choices = [m for m in metas if m.path not in used]
        if not choices:
            choices = pool[:] if pool else metas[:]

        if last_src:
            non_repeat = [m for m in choices if m.path != last_src]
            if non_repeat:
                choices = non_repeat

        # Don't use the loop clip immediately after or before the loop points
        if loop and loop_meta and (i == 1 or i == n - 2):
            non_loop = [m for m in choices if m.path != loop_meta.path]
            if non_loop:
                choices = non_loop

        if not choices:
            choices = metas

        meta = rng.choice(choices)
        used.add(meta.path)
        last_src = meta.path

        speed = float(rng.uniform(cfg.speed_min, cfg.speed_max))
        in_dur = float(out_dur * speed)

        margin = 0.08
        latest = max(0.0, meta.duration - in_dur - margin)
        start = float(rng.uniform(0.0, latest)) if latest > 0.1 else 0.0

        segments[i] = Segment(
            src=meta.path,
            in_start=max(0.0, start),
            in_dur=max(0.05, in_dur),
            out_dur=float(out_dur),
            speed=speed,
            motion=float(meta.motion),
        )

    # Cast segments back to list[Segment] since we filled all None
    segments = [s for s in segments if s is not None]
    
    duration = float(sum(s.out_dur for s in segments))
    # Hard clamp just in case
    if duration > cfg.max_duration_s:
        # Trim from end
        while segments and duration > cfg.max_duration_s + 1e-6:
            last = segments[-1]
            if last.out_dur <= 0.15:
                segments.pop()
                duration = float(sum(s.out_dur for s in segments))
                continue
            new_out = max(0.15, last.out_dur - (duration - cfg.max_duration_s))
            new_in = new_out * last.speed
            segments[-1] = Segment(
                src=last.src,
                in_start=last.in_start,
                in_dur=new_in,
                out_dur=new_out,
                speed=last.speed,
                motion=last.motion,
            )
            duration = float(sum(s.out_dur for s in segments))

    # Collect unique video paths used
    used_video_paths = list(dict.fromkeys([s.src for s in segments]))
    
    return EditPlan(segments=segments, duration=duration, used_videos=used_video_paths)
