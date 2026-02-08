from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests


@dataclass(frozen=True)
class FFmpegBinaries:
    ffmpeg: str
    ffprobe: str


def _run_capture(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)


def ensure_ffmpeg(tools_dir: str) -> FFmpegBinaries:
    """Locate FFmpeg/FFprobe; if missing, download a build into tools_dir/ffmpeg."""
    tools_path = Path(tools_dir)
    sys_platform = platform.system().lower()
    is_win = sys_platform == "windows"
    suffix = ".exe" if is_win else ""

    # 1. Try system PATH first, but VERIFY drawtext support
    ffmpeg_in_path = shutil.which("ffmpeg")
    ffprobe_in_path = shutil.which("ffprobe")
    if ffmpeg_in_path and ffprobe_in_path:
        try:
            res = subprocess.run([ffmpeg_in_path, "-filters"], capture_output=True, text=True)
            if "drawtext" in res.stdout:
                return FFmpegBinaries(ffmpeg=ffmpeg_in_path, ffprobe=ffprobe_in_path)
            else:
                print(f"System FFmpeg at {ffmpeg_in_path} lacks 'drawtext' filter. Looking for a better one...")
        except Exception:
            pass

    # 2. Check local tools dir
    local_bin = tools_path / "ffmpeg" / "bin"
    local_ffmpeg = local_bin / f"ffmpeg{suffix}"
    local_ffprobe = local_bin / f"ffprobe{suffix}"
    
    if local_ffmpeg.exists() and local_ffprobe.exists():
        try:
            res = subprocess.run([str(local_ffmpeg), "-filters"], capture_output=True, text=True)
            if "drawtext" in res.stdout:
                return FFmpegBinaries(ffmpeg=str(local_ffmpeg), ffprobe=str(local_ffprobe))
        except Exception:
            pass

    # 3. Download if needed
    tools_path.mkdir(parents=True, exist_ok=True)
    
    if is_win:
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        archive = tools_path / "ffmpeg_release_essentials.zip"
    elif sys_platform == "darwin":
        # Evermeet constant URL for latest static release
        url = "https://evermeet.cx/ffmpeg/getrelease/zip"
        archive = tools_path / "ffmpeg_macos.zip"
    else:
        raise RuntimeError(f"FFmpeg with drawtext not found and auto-download not implemented for {sys_platform}")

    print(f"Downloading FFmpeg from {url}...")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(archive, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    extract_root = tools_path / "ffmpeg_temp"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    print(f"Extracting {archive}...")
    with zipfile.ZipFile(archive, "r") as z:
        z.extractall(extract_root)

    # Locate binaries in extracted files
    if is_win:
        candidates = list(extract_root.glob("**/bin/ffmpeg.exe"))
    else:
        # macOS zip from evermeet usually contains 'ffmpeg' at the root or in a folder
        candidates = list(extract_root.glob("**/ffmpeg"))
        # Filter out directories
        candidates = [c for c in candidates if c.is_file() and not c.is_dir()]

    if not candidates:
        raise RuntimeError(f"Could not find ffmpeg binary in {archive}")

    target_ffmpeg = candidates[0]
    
    # ffprobe is often a separate download on evermeet, but we'll check if it's there
    target_ffprobe = target_ffmpeg.parent / f"ffprobe{suffix}"
    
    if not target_ffprobe.exists() and sys_platform == "darwin":
        print("FFprobe not found in ffmpeg zip, downloading separately...")
        probe_url = "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"
        probe_archive = tools_path / "ffprobe_macos.zip"
        with requests.get(probe_url, stream=True, timeout=120) as r:
            with open(probe_archive, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024): f.write(chunk)
        with zipfile.ZipFile(probe_archive, "r") as z:
            z.extractall(extract_root / "probe")
        probe_candidates = list((extract_root / "probe").glob("**/ffprobe"))
        if probe_candidates:
            target_ffprobe = probe_candidates[0]

    if not target_ffprobe.exists():
        # Fallback to system ffprobe if local one failed to download/extract
        system_ffprobe = shutil.which("ffprobe")
        if system_ffprobe:
            target_ffprobe = Path(system_ffprobe)
        else:
            raise RuntimeError("Could not find ffprobe binary.")

    # Move to final location
    local_bin.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target_ffmpeg), str(local_ffmpeg))
    shutil.move(str(target_ffprobe), str(local_ffprobe))
    
    # Permissions
    if not is_win:
        local_ffmpeg.chmod(0o755)
        local_ffprobe.chmod(0o755)

    shutil.rmtree(extract_root)
    return FFmpegBinaries(ffmpeg=str(local_ffmpeg), ffprobe=str(local_ffprobe))


def ffprobe_json(ffprobe_path: str, media_path: str) -> dict[str, Any]:
    args = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        media_path,
    ]
    cp = _run_capture(args)
    if cp.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {media_path}:\n{cp.stdout}")
    return json.loads(cp.stdout)


def list_ffmpeg_encoders(ffmpeg_path: str) -> str:
    cp = _run_capture([ffmpeg_path, "-hide_banner", "-encoders"])
    return cp.stdout


def list_ffmpeg_hwaccels(ffmpeg_path: str) -> str:
    cp = _run_capture([ffmpeg_path, "-hide_banner", "-hwaccels"])
    return cp.stdout


def list_ffmpeg_filters(ffmpeg_path: str) -> str:
    cp = _run_capture([ffmpeg_path, "-hide_banner", "-filters"])
    return cp.stdout


def run_ffmpeg(ffmpeg_path: str, args: list[str], *, stream_output: bool = True) -> None:
    """Run FFmpeg.

    When stream_output=True, mirrors FFmpeg output to stdout in real time so
    long renders are observable from the terminal.
    """

    full = [ffmpeg_path] + args

    if not stream_output:
        proc = subprocess.run(full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stdout)
        return

    # Stream output line-by-line for progress visibility.
    # Keep a tail buffer for error reporting.
    tail: deque[str] = deque(maxlen=300)

    proc = subprocess.Popen(
        full,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    assert proc.stdout is not None
    for line in proc.stdout:
        tail.append(line)
        sys.stdout.write(line)
        sys.stdout.flush()

    rc = proc.wait()
    if rc != 0:
        raise RuntimeError("".join(tail))


def safe_relpath(path: str, start: str) -> str:
    try:
        return os.path.relpath(path, start)
    except Exception:
        return path


def which_first(paths: Iterable[str]) -> str | None:
    for p in paths:
        if p and Path(p).exists():
            return p
    return None
