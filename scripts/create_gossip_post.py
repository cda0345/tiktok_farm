#!/usr/bin/env python3
"""Create a TikTok-style gossip short from the first item of a gossip RSS feed.

Flow:
1) Read first news item from popular gossip feeds.
2) Resolve a representative image for the article.
3) Render a vertical short (9:16) with headline overlay.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.ffmpeg_utils import ensure_ffmpeg, run_ffmpeg
from core.ai_client import OpenAIConfig, is_openai_configured


FEED_PROFILES: dict[str, list[tuple[str, str]]] = {
    "br": [
        ("contigo", "https://contigo.com.br/feed"),
        ("ofuxico", "https://ofuxico.com.br/wp-json/wp/v2/posts?per_page=10&_embed=1"),
        ("terra_gente", "https://www.terra.com.br/diversao/gente/rss.xml"),
        ("ig_gente", "https://gente.ig.com.br/rss.xml"),
    ],
    "intl": [
        ("tmz", "https://www.tmz.com/rss.xml"),
        ("pagesix", "https://pagesix.com/feed/"),
        ("perezhilton", "https://perezhilton.com/feed/"),
    ],
}

# Configurações do Telegram
# Prefer env vars (for GitHub Actions secrets). Fallback kept for local usage.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8519683231:AAH1RsrgaYmo3v99hd_yfktgoFWHU2AWrP0"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "1015015823"  # ID padrão para recebimento, pode ser ajustado se necessário


@dataclass(frozen=True)
class NewsItem:
    source: str
    feed_url: str
    title: str
    link: str
    published: str
    image_url: str
    description: str = ""


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1].lower()
    return tag.lower()


def _clean_text(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "")).strip()


def _extract_first_img_from_html(html: str) -> str | None:
    patterns = [
        r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)",
        r"<meta[^>]+name=[\"']twitter:image[\"'][^>]+content=[\"']([^\"']+)",
        r"<img[^>]+src=[\"']([^\"']+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            url = match.group(1).strip()
            if url.startswith("http"):
                return url
    return None


def _strip_html(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"&nbsp;|&#160;", " ", t, flags=re.I)
    t = re.sub(r"&amp;", "&", t, flags=re.I)
    t = re.sub(r"&quot;", '"', t, flags=re.I)
    return _clean_text(t)


def _extract_article_text(link: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; GossipPostBot/1.0)"}
        html = requests.get(link, headers=headers, timeout=30).text
    except Exception:
        return ""

    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.I | re.S)
    cleaned = [_strip_html(p) for p in paragraphs]
    cleaned = [p for p in cleaned if len(p) >= 35]
    text = " ".join(cleaned[:8])
    return _clean_text(text)[:1200]


def _image_from_item(item: ET.Element) -> str | None:
    # Common RSS image slots
    for child in list(item):
        tag = _local_name(child.tag)
        if tag in {"content", "thumbnail"}:  # media:content / media:thumbnail
            candidate = (child.attrib.get("url") or "").strip()
            if candidate.startswith("http"):
                return candidate
        if tag == "enclosure":
            candidate = (child.attrib.get("url") or "").strip()
            mime = (child.attrib.get("type") or "").lower()
            if candidate.startswith("http") and ("image" in mime or re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", candidate, re.I)):
                return candidate

    # Sometimes description contains an image tag
    desc = item.findtext("description") or ""
    desc_img = _extract_first_img_from_html(desc)
    if desc_img:
        return desc_img

    return None


def _fetch_first_news(feeds: list[tuple[str, str]]) -> NewsItem:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GossipPostBot/1.0)"}

    for source_name, feed_url in feeds:
        try:
            resp = requests.get(feed_url, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception:
            continue

        body = resp.text or ""
        ctype = (resp.headers.get("content-type") or "").lower()

        # Some sources expose latest posts via WordPress JSON instead of RSS.
        if "json" in ctype or body.lstrip().startswith("["):
            try:
                posts = resp.json()
            except Exception:
                continue
            if not isinstance(posts, list):
                continue
            for post in posts:
                if not isinstance(post, dict):
                    continue
                title = _strip_html((post.get("title") or {}).get("rendered") or "")
                link = _clean_text(post.get("link") or "")
                published = _clean_text(post.get("date") or "")
                description = _strip_html((post.get("excerpt") or {}).get("rendered") or "")
                if not title or not link:
                    continue

                image_url = ""
                embedded = post.get("_embedded") or {}
                media = embedded.get("wp:featuredmedia") or []
                if media and isinstance(media[0], dict):
                    image_url = _clean_text(media[0].get("source_url") or "")

                if not image_url:
                    try:
                        article_resp = requests.get(link, headers=headers, timeout=30)
                        article_resp.raise_for_status()
                        image_url = _extract_first_img_from_html(article_resp.text) or ""
                    except Exception:
                        image_url = ""

                if image_url and image_url.startswith("http"):
                    return NewsItem(
                        source=source_name,
                        feed_url=feed_url,
                        title=title,
                        link=link,
                        published=published,
                        image_url=image_url,
                        description=description,
                    )
            continue

        try:
            root = ET.fromstring(body)
        except Exception:
            continue

        items = root.findall("./channel/item")
        for item in items:
            title = _clean_text(item.findtext("title"))
            link = _clean_text(item.findtext("link"))
            published = _clean_text(item.findtext("pubDate"))
            description = _strip_html(item.findtext("description") or "")
            if not title or not link:
                continue

            image_url = _image_from_item(item)
            if not image_url:
                try:
                    article_resp = requests.get(link, headers=headers, timeout=30)
                    article_resp.raise_for_status()
                    image_url = _extract_first_img_from_html(article_resp.text)
                except Exception:
                    image_url = None

            if image_url and image_url.startswith("http"):
                return NewsItem(
                    source=source_name,
                    feed_url=feed_url,
                    title=title,
                    link=link,
                    published=published,
                    image_url=image_url,
                    description=description,
                )

    raise RuntimeError("No gossip item with usable image found in configured feeds.")


def _guess_extension(image_url: str, content_type: str) -> str:
    parsed = urlparse(image_url)
    ext = Path(parsed.path).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return ext

    if content_type:
        from_mime = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if from_mime:
            return ".jpg" if from_mime == ".jpe" else from_mime

    return ".jpg"


def _upgrade_image_url(url: str) -> str:
    return re.sub(r"-\d{2,4}x\d{2,4}(?=\.(jpg|jpeg|png|webp)(\?|$))", "", url, flags=re.I)


def _download_image(url: str, out_base: Path) -> Path:
    if not url or not url.startswith("http"):
        raise RuntimeError(f"Invalid image URL provided: '{url}'")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GossipPostBot/1.0)"}
    candidates = []
    upgraded = _upgrade_image_url(url)
    if upgraded != url:
        candidates.append(upgraded)
    candidates.append(url)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            with requests.get(candidate, headers=headers, stream=True, timeout=60) as r:
                r.raise_for_status()
                ext = _guess_extension(candidate, r.headers.get("content-type", ""))
                out_path = out_base.with_suffix(ext)
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            if out_path.exists() and out_path.stat().st_size >= 10 * 1024:
                return out_path
        except Exception as exc:
            last_error = exc
            continue

    if last_error:
        raise RuntimeError(f"Failed to download usable image: {last_error}") from last_error
    raise RuntimeError("Failed to download usable image.")


def _make_slug(text: str, max_words: int = 5) -> str:
    """Cria um slug amigável e limpo para arquivos e pastas."""
    import unicodedata
    normalized = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', normalized).lower()
    return "-".join(clean.split()[:max_words])


def _select_font() -> str:
    # Condensed, editorial look closer to gossip portals.
    candidates = [
        "/System/Library/Fonts/Supplemental/Avenir Next Condensed Heavy.ttf",
        "/System/Library/Fonts/Supplemental/Avenir Next Condensed Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
        "/System/Library/Fonts/Supplemental/ChalkboardSE-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Futura-CondensedExtraBold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "/System/Library/Fonts/Helvetica.ttc"


def _ffmpeg_escape(path: str) -> str:
    return (
        path.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
    )


def _sanitize_overlay_text(text: str) -> str:
    # Remove hidden/control Unicode chars that may render as small boxes.
    text = (text or "").replace("\r", "")
    text = re.sub(r"[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]", "", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ffmpeg_escape_text(text: str) -> str:
    t = _sanitize_overlay_text(text)
    return (
        t.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("%", "\\%")
        .replace("\n", "\\n")
    )


def _estimate_logo_bg_color(logo_path: Path) -> str:
    """Estimate a background hex color from logo border pixels."""
    try:
        from PIL import Image

        img = Image.open(logo_path).convert("RGBA")
        px = img.load()
        w, h = img.size
        samples: list[tuple[int, int, int]] = []

        band_x = max(1, w // 12)
        band_y = max(1, h // 12)

        for x in range(w):
            for y in list(range(0, band_y)) + list(range(max(0, h - band_y), h)):
                r, g, b, a = px[x, y]
                if a > 200:
                    samples.append((r, g, b))

        for y in range(h):
            for x in list(range(0, band_x)) + list(range(max(0, w - band_x), w)):
                r, g, b, a = px[x, y]
                if a > 200:
                    samples.append((r, g, b))

        if not samples:
            r, g, b = img.convert("RGB").resize((1, 1)).getpixel((0, 0))
            return f"0x{r:02X}{g:02X}{b:02X}"

        r = sum(c[0] for c in samples) // len(samples)
        g = sum(c[1] for c in samples) // len(samples)
        b = sum(c[2] for c in samples) // len(samples)
        return f"0x{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "0xC70000"


def _wrap_for_overlay(text: str, max_chars: int, max_lines: int, *, upper: bool = False) -> str:
    clean = _clean_text(text)
    if upper:
        clean = clean.upper()
    wrapped = textwrap.wrap(clean, width=max_chars)
    # We prioritize showing the full message without "..." suffixes
    return "\n".join(wrapped[:max_lines])


def _pick_pt_hook(headline: str) -> str:
    h = _clean_text(headline).lower()
    if any(k in h for k in ["morre", "morte", "luto", "velório", "velorio"]):
        return "LUTO NO MUNDO DOS FAMOSOS"
    if any(k in h for k in ["bbb", "a fazenda", "reality"]):
        return "TRETA NO REALITY"
    if any(k in h for k in ["filha", "filho", "bebê", "bebe", "gravidez"]):
        return "FOFURA E EMOÇÃO"
    if any(k in h for k in ["separ", "divórcio", "divorcio", "trai", "polêmica", "polemica"]):
        return "DEU O QUE FALAR"
    return "FOFOCA DO MOMENTO"


def _pick_en_hook(headline: str) -> str:
    h = _clean_text(headline).lower()
    if any(k in h for k in ["dies", "death", "dead", "passed away", "funeral"]):
        return "SHOCKING LOSS"
    if any(k in h for k in ["split", "divorce", "cheat", "scandal"]):
        return "MAJOR CELEB DRAMA"
    if any(k in h for k in ["baby", "pregnan", "daughter", "son"]):
        return "BIG FAMILY UPDATE"
    return "TRENDING CELEB TEA"


def _is_portuguese_context(source: str, headline: str) -> bool:
    # Strict check for BR portals
    if source in {"contigo", "ofuxico", "terra_gente", "ig_gente"}:
        return True
    h = _clean_text(headline).lower()
    pt_markers = [" não ", " com ", " para ", " dos ", " das ", "você", "fofoca", "famosos", " é ", " o ", " a "]
    return any(m in h for m in pt_markers)


def _build_text_layers(headline: str, source: str) -> tuple[str, str]:
    clean = _clean_text(headline)
    # Build a more specific top hook from the actual headline, not a generic tag.
    # 1) Prefer the first semantic chunk before separators.
    # 2) Fallback to the first 8 words.
    chunk = re.split(r"\s*[-:|]\s*", clean, maxsplit=1)[0].strip()
    if len(chunk.split()) < 3:
        chunk = " ".join(clean.split()[:8]).strip()

    # Light cleanup to keep the hook punchy.
    chunk = chunk.replace("‘", "").replace("’", "").replace("“", "").replace("”", "")
    chunk = re.sub(r"^[\"':;,.!?-]+|[\"':;,.!?-]+$", "", chunk)
    chunk = re.sub(r"\b(veja|entenda|saiba|assista)\b", "", chunk, flags=re.I)
    chunk = _clean_text(chunk)

    # If chunk is still too short/weak, fallback to the old generic style.
    if len(chunk.split()) < 2:
        is_pt = _is_portuguese_context(source, clean)
        chunk = _pick_pt_hook(clean) if is_pt else _pick_en_hook(clean)

    # Aumentando para 3 linhas no Hook para prevenir cortes em palavras grandes
    hook = _wrap_for_overlay(chunk, max_chars=20, max_lines=3, upper=True)

    # Bottom text: summarized detail.
    summary = _wrap_for_overlay(clean, max_chars=25, max_lines=4, upper=False)
    return hook, summary


def _headline_for_overlay(headline: str, max_chars: int = 24, max_lines: int = 5) -> str:
    # Backward-compat helper for scripts that still call this.
    return _wrap_for_overlay(headline, max_chars=max_chars, max_lines=max_lines, upper=True)


def _build_display_headline(headline: str) -> str:
    # Portal-style, bold and concise.
    # Increased lines to 8 to prevent cutting sentences.
    return _wrap_for_overlay(headline, max_chars=28, max_lines=8, upper=True)


def _summarize_news_text(item: NewsItem) -> str:
    is_pt = _is_portuguese_context(item.source, item.title)
    article_text = _extract_article_text(item.link)
    context = _clean_text(f"{item.title}. {item.description}. {article_text}")
    context = context[:2200]

    cfg = OpenAIConfig()
    if is_openai_configured(cfg):
        try:
            api_key = os.getenv(cfg.api_key_env, "").strip()
            url = f"{cfg.base_url.rstrip('/')}/chat/completions"
            
            if is_pt:
                system_instr = (
                    "Você é um editor de vídeos Curtos/TikTok especializado em fofocas e entretenimento. "
                    "REGRAS OBRIGATÓRIAS:\n"
                    "1. GANCHO (HOOK): Uma frase ULTRA CURTA com o clímax (MÁXIMO 5 PALAVRAS, TUDO EM MAIÚSCULAS). EXEMPLOS: 'NEYMAR EM POLÊMICA!', 'BBB: TRETA PESADA!', 'FAMOSA ANUNCIA GRAVIDEZ!'\n"
                    "2. CORPO: Resuma o fato principal em 1-2 frases curtas (máx 15 palavras TOTAL, TUDO EM MAIÚSCULAS).\n"
                    "3. LOOP/CTA: Termine com uma pergunta curta e impactante (máx 8 palavras, TUDO EM MAIÚSCULAS).\n"
                    "4. HASHTAGS: Inclua 3 hashtags relevantes para SEO no final em LETRAS MINÚSCULAS.\n"
                    "IMPORTANTE: Exceto as hashtags, o texto deve estar TODO EM LETRA MAIÚSCULA.\n"
                    "5. IDIOMA: Português do Brasil. Sem aspas ou emojis.\n"
                    "6. FORMATO: Responda com as 4 linhas separadas, cada uma em uma linha nova."
                )
                user_content = f"Crie o roteiro curto para esta notícia:\n\n{context}"
            else:
                system_instr = (
                    "You are a Shorts/TikTok editor specialized in celebrity gossip."
                    "MANDATORY RULES:\n"
                    "1. HOOK: Start with the climax/shock (max 6 words, ALL CAPS).\n"
                    "2. BODY: Summarize the fact in one short sentence (max 8 words, ALL CAPS).\n"
                    "3. LOOP/CTA: End with a short provocative question (max 10 words, ALL CAPS).\n"
                    "4. HASHTAGS: Include 3 relevant SEO hashtags at the end in LOWERCASE.\n"
                    "5. FORMAT: 4 lines (Hook, Body, CTA, Hashtags), no quotes, no emojis."
                )
                user_content = f"Create a short script for this news:\n\n{context}"

            payload = {
                "model": cfg.model,
                "temperature": 0.5,
                "messages": [
                    {"role": "system", "content": system_instr},
                    {"role": "user", "content": user_content},
                ],
            }
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if r.status_code < 400:
                data = r.json()
                content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
                if content:
                    return _clean_text(str(content)).replace(" | ", "\n").replace("; ", "\n")
        except Exception:
            pass

    # Local fallback: compress title while preserving key info.
    title = _clean_text(item.title)
    base = re.split(r"\s*[-:|]\s*", title, maxsplit=1)
    if len(base) == 2:
        summary = f"{base[0]}: {base[1]}."
    else:
        summary = title if title.endswith(".") else (title + ".")
    return _clean_text(summary)


def _send_video_to_telegram(video_path: Path, caption: str) -> bool:
    """Envia o vídeo gerado para o bot do Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    try:
        with open(video_path, "rb") as video:
            files = {"video": video}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
            response = requests.post(url, files=files, data=data, timeout=120)
            if response.status_code == 200:
                print(f"✅ Vídeo enviado com sucesso para o Telegram!")
                return True
            else:
                print(f"❌ Erro ao enviar para o Telegram: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        print(f"⚠️ Falha ao tentar enviar para o Telegram: {e}")
        return False


def _send_text_to_telegram(text: str) -> bool:
    """Envia uma mensagem de texto simples para o bot do Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        response = requests.post(url, data=data, timeout=30)
        return response.status_code == 200
    except Exception:
        return False


def _render_short(
    image_path: Path,
    headline_file: Path,
    source: str,
    out_video: Path,
    *,
    hook_file: Path | None = None,
    summary_file: Path | None = None,
    cta_text: str = "INSCREVA-SE",
    logo_path: Path | None = None,
) -> None:
    ff = ensure_ffmpeg("tools")
    font = _ffmpeg_escape(_select_font())
    duration_s = 5
    fade_out_start = max(0.0, duration_s - 1.2)
    cta_escaped = _ffmpeg_escape_text(cta_text.upper())
    overlay_dir = out_video.parent / "_overlay_text"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    hook_box_color = "0x000000"
    main_path = summary_file or headline_file
    main_raw = main_path.read_text(encoding="utf-8") if main_path.exists() else ""
    main_lines = [ln.strip() for ln in _sanitize_overlay_text(main_raw).replace("\xa0", " ").splitlines() if ln.strip()]
    if not main_lines:
        main_lines = ["SEM TEXTO"]

    hook_raw = hook_file.read_text(encoding="utf-8") if hook_file and hook_file.exists() else ""
    hook_lines = [ln.strip() for ln in _sanitize_overlay_text(hook_raw).replace("\xa0", " ").splitlines() if ln.strip()]
    if not hook_lines:
        hook_lines = ["FOFOCA DO MOMENTO"]

    # Render hook text - use manual line breaking for compatibility
    hook_text_content = "\n".join(hook_lines[:3])
    hook_text_file = overlay_dir / "hook_block.txt"
    hook_text_file.write_text(_sanitize_overlay_text(hook_text_content) + "\n", encoding="utf-8")
    hook_text_escaped = _ffmpeg_escape(str(hook_text_file.resolve()))
    
    hook_draw = (
        f"drawtext=textfile='{hook_text_escaped}':fontfile='{font}':"
        "fontcolor=white:fontsize=68:line_spacing=15:fix_bounds=1:"
        f"box=1:boxcolor={hook_box_color}@0.96:boxborderw=20:"
        "x=(w-tw)/2:y=420,"
    )

    # Render main headline - break lines manually for better compatibility
    # Split long headline into multiple lines (max ~35 chars per line for better fit)
    import textwrap
    wrapped_lines = []
    for line in main_lines[:8]:
        # Wrap each line to max 35 characters, preserving word boundaries
        wrapped_lines.extend(textwrap.wrap(line, width=35, break_long_words=False, break_on_hyphens=False))
    
    main_text_content = "\n".join(wrapped_lines[:6])  # Max 6 lines
    main_text_file = overlay_dir / "main_block.txt"
    main_text_file.write_text(_sanitize_overlay_text(main_text_content) + "\n", encoding="utf-8")
    main_text_escaped = _ffmpeg_escape(str(main_text_file.resolve()))
    
    main_draw = (
        f"drawtext=textfile='{main_text_escaped}':fontfile='{font}':"
        "fontcolor=white:fontsize=56:line_spacing=15:fix_bounds=1:"
        "x=(w-tw)/2:y=1150,"
    )

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
        "eq=brightness=-0.02:contrast=1.08:saturation=1.02,"
        f"{hook_draw}"
        # Bottom cinematic fade for headline readability - ajustado para o novo posicionamento
        "drawbox=x=0:y=ih*0.56:w=iw:h=ih*0.44:color=black@0.22:t=fill,"
        "drawbox=x=0:y=ih*0.66:w=iw:h=ih*0.34:color=black@0.42:t=fill,"
        "drawbox=x=0:y=ih*0.76:w=iw:h=ih*0.24:color=black@0.62:t=fill,"
        # Headline block.
        f"{main_draw}"
        # Subtle CTA in footer, less intrusive than previous style.
        f"drawtext=text='{cta_escaped}':fontfile='{font}':fontcolor=white@0.88:"
        "fontsize=44:x=(w-text_w)/2:y=h*0.94:enable='lt(mod(t\\,1.4)\\,0.7)'"
    )

    out_video.parent.mkdir(parents=True, exist_ok=True)

    if logo_path is not None and logo_path.exists():
        # Overlay logo at top-center with subtle scale while preserving alpha.
        args = [
            "-hide_banner",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-t",
            str(duration_s),
            "-i",
            str(image_path),
            "-i",
            str(logo_path),
            "-f",
            "lavfi",
            "-t",
            str(duration_s),
            "-i",
            "sine=frequency=247:sample_rate=44100",
            "-filter_complex",
            f"[0:v]{vf}[bg];[1:v]scale='360+34*sin(2*PI*n/72)':-1:eval=frame[logo];[bg][logo]overlay=(W-w)/2:36[v]",
            "-map",
            "[v]",
            "-map",
            "2:a:0",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-af",
            f"volume=0.06,lowpass=f=1200,afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_start:.1f}:d=1.2",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out_video),
        ]
    else:
        args = [
            "-hide_banner",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-t",
            str(duration_s),
            "-i",
            str(image_path),
            "-f",
            "lavfi",
            "-t",
            str(duration_s),
            "-i",
            "sine=frequency=247:sample_rate=44100",
            "-vf",
            vf,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-af",
            f"volume=0.06,lowpass=f=1200,afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_start:.1f}:d=1.2",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out_video),
        ]
    run_ffmpeg(ff.ffmpeg, args, stream_output=False)


def create_post_for_item(item: NewsItem, args: argparse.Namespace) -> bool:
    """Função centralizada para criar um post a partir de um NewsItem."""
    root = Path(__file__).resolve().parents[1]
    post_dir = root / "gossip_post"
    post_dir.mkdir(parents=True, exist_ok=True)

    try:
        image_path = _download_image(item.image_url, post_dir / "news_image")

        # Get the smart summary first to use as hook/headline
        raw_script = _summarize_news_text(item)
        all_lines = [ln.strip() for ln in raw_script.splitlines() if ln.strip()]
        
        # Filtro robusto: separa hashtags de qualquer outra linha e força minúsculas
        hashtags = " ".join([ln.lower() for ln in all_lines if ln.startswith("#")])
        ai_parts = [ln for ln in all_lines if not ln.startswith("#")]
        
        if len(ai_parts) >= 2:
            # Hook com limite maior de caracteres (25) para não cortar palavras
            hook_raw = ai_parts[0]
            # Se o hook da IA for muito longo, pega apenas as primeiras 5 palavras mais impactantes
            hook_words = hook_raw.split()
            if len(hook_words) > 5:
                hook = " ".join(hook_words[:5])
            else:
                hook = hook_raw
            headline_text = "\n".join(ai_parts[1:])
        else:
            # Fallback: cria hook curto e impactante do título
            hook, summary = _build_text_layers(item.title, item.source)
            # Limita o hook a 5 palavras no fallback também
            hook_words = hook.split()
            if len(hook_words) > 5:
                hook = " ".join(hook_words[:5])
            headline_text = "\n".join(ai_parts) if ai_parts else summary

        # Remove hashtags do headline_text para o vídeo
        headline_text_clean = re.sub(r'#\w+', '', headline_text).strip()
        headline_text_clean = re.sub(r'\s+', ' ', headline_text_clean)  # Remove espaços extras
        
        # Garante o wrap do hook vindo da IA com mais caracteres por linha
        hook = _wrap_for_overlay(hook, max_chars=30, max_lines=3, upper=True)
        
        hook_file = post_dir / "hook.txt"
        hook_file.write_text(_sanitize_overlay_text(hook) + "\n", encoding="utf-8")

        summary_file = post_dir / "summary.txt"
        summary_file.write_text(_sanitize_overlay_text(headline_text_clean) + "\n", encoding="utf-8")

        # Display headline: concise summary of the full news message.
        headline = _build_display_headline(headline_text_clean)
        headline_file = post_dir / "headline.txt"
        headline_file.write_text(_sanitize_overlay_text(headline) + "\n", encoding="utf-8")

        # Keep source metadata for traceability and later automation.
        metadata = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": item.source,
            "feed_url": item.feed_url,
            "title": item.title,
            "article_url": item.link,
            "published": item.published,
            "image_url": item.image_url,
            "local_image": str(image_path.relative_to(root)),
        }
        (post_dir / "news.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        (post_dir / "caption.txt").write_text(
            f"{hook}\n{headline_text_clean}\n\n{hashtags}\n\nFonte: {item.source.upper()}\nLink: {item.link}\n",
            encoding="utf-8",
        )

        slug = _make_slug(item.title)
        output_video = post_dir / "output" / f"gossip_{slug}.mp4"
        cta_text = "INSCREVA-SE" if _is_portuguese_context(item.source, item.title) else "SUBSCRIBE"
        logo_path = None
        if args.logo:
            logo_path = Path(args.logo).expanduser().resolve()
        else:
            for name in ("logo.png", "logo.webp", "logo.jpg", "logo.jpeg"):
                candidate = post_dir / name
                if candidate.exists():
                    logo_path = candidate
                    break
        _render_short(
            image_path,
            headline_file,
            item.source,
            output_video,
            hook_file=hook_file,
            summary_file=headline_file,
            cta_text=cta_text,
            logo_path=logo_path,
        )

        # Telegram Notification with hashtags in caption
        # Clean up hook and headline for better formatting
        hook_clean = " ".join(hook.split())  # Remove extra spaces/newlines
        headline_clean = " ".join(headline_text_clean.split())  # Single line
        
        telegram_caption = (
            f"🔥 {hook_clean}\n\n"
            f"{headline_clean}\n\n"
            f"{hashtags}\n\n"
            f"📍 Fonte: {item.source.upper()}\n"
            f"🔗 {item.link}"
        )
        _send_video_to_telegram(output_video, telegram_caption)

        print("=" * 64)
        print(f"✅ Post concluído: {item.title}")
        print(f"Vídeo: {output_video}")
        print("=" * 64)
        return True
    except Exception as e:
        print(f"❌ Erro ao criar post para '{item.title}': {e}")
        return False


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create one gossip short from RSS feeds.")
    p.add_argument("--profile", choices=("br", "intl"), default="br")
    p.add_argument("--logo", default="", help="Optional logo path (png/webp/jpg).")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    feeds = FEED_PROFILES[args.profile]
    item = _fetch_first_news(feeds)
    create_post_for_item(item, args)


if __name__ == "__main__":
    main()
