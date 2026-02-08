from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests
import random
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class OpenAIConfig:
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"


def is_openai_configured(cfg: OpenAIConfig) -> bool:
    v = os.getenv(cfg.api_key_env, "").strip()
    return bool(v)


def generate_caption_and_hashtags(*, themes: list[str], track_id: str = "", niche: str, cfg: OpenAIConfig) -> tuple[str, str]:
    """Returns (caption_line1, hashtags_line2). Uses cheapest default model.

    Requires OPENAI_API_KEY in environment.
    """

    api_key = os.getenv(cfg.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Missing {cfg.api_key_env} env var")

    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": cfg.model,
        "temperature": 1.0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a curator for an aesthetic house music channel. You write extremely minimalist, sophisticated captions inspired by the song's atmosphere or lyrics. No emojis. No artist/track names."
            },
            {
                "role": "user",
                "content": (
                    f"Create a minimalist caption for the song: {track_id.replace('_', ' ')}.\n"
                    f"Visual Themes: {', '.join(themes)}.\n\n"
                    "Output as JSON with keys: caption, hashtags.\n"
                    "Rules:\n"
                    "- caption: 2-4 words maximum. Avoid 'vibes', 'groove', 'energy', 'mood'. Be sensorial or poetic.\n"
                    "- hashtags: 4-5 total. Start with #housemusic, end with #fyp. Context tags in between.\n"
                ),
            }
        ],
    }

    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(r.text)

    data: dict[str, Any] = r.json()
    content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
    if not content:
        raise RuntimeError("OpenAI returned empty content")

    import json

    obj: dict[str, Any] = json.loads(content)
    caption = str(obj.get("caption", "")).strip()
    hashtags = str(obj.get("hashtags", "")).strip()

    if not caption or not hashtags:
        raise RuntimeError("OpenAI JSON missing caption/hashtags")

    return caption, hashtags


def generate_final_caption(*, themes: list[str], niche: str, track_id: str, cfg: OpenAIConfig) -> str:
    """Returns a human-facing caption ready to paste on TikTok/Reels.

    The output is plain text (not JSON). It may include TrackID and hashtags in the body.
    """

    api_key = os.getenv(cfg.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Missing {cfg.api_key_env} env var")

    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": cfg.model,
        "temperature": 1.0,
        "messages": [
            {
                "role": "system",
                "content": "You are a curator for an aesthetic house music channel. You write extremely minimalist, sophisticated captions inspired by the iconic song's soul. No emojis."
            },
            {
                "role": "user",
                "content": (
                    f"Write a 1-line minimalist caption for a reel featuring the track: {track_id.replace('_', ' ')}.\n"
                    f"Themes: {', '.join(themes)}.\n\n"
                    "Rules:\n"
                    "- 2 to 4 words total.\n"
                    "- No artist or track names.\n"
                    "- Be sensorial, abstract, or inspired by the song's meaning.\n"
                    "- NO 'vibes', 'groove', 'energy', 'mood'.\n"
                    "- Followed by 4-5 hashtags starting with #housemusic and ending with #fyp.\n"
                    "Format: [Caption]. #hashtag1 #hashtag2 #fyp"
                ),
            }
        ],
    }

    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(r.text)

    data: dict[str, Any] = r.json()
    content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
    if not content:
        raise RuntimeError("OpenAI returned empty content")

    return str(content).strip()
