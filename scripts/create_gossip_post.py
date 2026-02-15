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
import random
import hashlib

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.ffmpeg_utils import ensure_ffmpeg, run_ffmpeg
from core.ai_client import OpenAIConfig, is_openai_configured


# CTAs (Call-to-Action) para rotação aleatória
CTA_VARIATIONS = [
    "INSCREVA-SE",           # Original - clássico
    "👉 SEGUE PRA MAIS",     # Informal + direto
    "ATIVA O SININHO 🔔",    # Foco em notificação
    "PRÓXIMO É BOMBA 🔥",    # Cria curiosidade
    "SEGUE AQUI 👇",         # Direto com emoji
    "QUER MAIS? SEGUE",      # Value proposition
    "SALVA ESSE POST",       # Engajamento
    "MARCA UM AMIGO",        # Viralização
]


def _get_random_cta(seed_text: str = "") -> str:
    """Seleciona um CTA aleatório de forma determinística baseado no seed_text.
    
    Se seed_text for fornecido, o mesmo texto sempre retorna o mesmo CTA.
    Isso garante que re-processar o mesmo post mantém o mesmo CTA.
    """
    if seed_text:
        # Usa hash do texto como seed para ser determinístico
        hash_value = int(hashlib.md5(seed_text.encode()).hexdigest(), 16)
        random.seed(hash_value)
    
    cta = random.choice(CTA_VARIATIONS)
    
    # Reset random seed para não afetar outros randoms
    random.seed()
    
    return cta


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


def _fetch_news_from_url(url: str, source_name: str = "custom") -> NewsItem:
    """Fetch news data from a specific URL instead of RSS."""
    try:
        # Tenta extrair informações básicas via OpenGraph ou meta tags se possível
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        
        # Busca imagem (og:image)
        img_match = re.search(r'<meta property="og:image" content="([^"]+)"', r.text)
        image_url = img_match.group(1) if img_match else ""
        
        # Busca título (og:title ou <title>)
        title_match = re.search(r'<meta property="og:title" content="([^"]+)"', r.text)
        if not title_match:
            title_match = re.search(r'<title>([^<]+)</title>', r.text)
        
        title = title_match.group(1) if title_match else "Sem título"
        
        # Busca descrição
        desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', r.text)
        desc = desc_match.group(1) if desc_match else ""

        return NewsItem(
            source=source_name,
            feed_url=url,
            title=title.strip(),
            link=url,
            published=datetime.now(timezone.utc).isoformat(),
            image_url=image_url,
            description=desc.strip()
        )
    except Exception as e:
        print(f"⚠️ Erro ao buscar notícia via URL direta: {e}")
        # Retorna um item mínimo para tentar processar
        return NewsItem(
            source=source_name,
            feed_url=url,
            title="Notícia via Telegram",
            link=url,
            published=datetime.now(timezone.utc).isoformat(),
            image_url="",
            description=""
        )


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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com"
    }
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


def _smart_truncate_hook(hook_raw: str, max_words: int = 5) -> str:
    """Trunca o gancho de forma inteligente para não cortar no meio de uma expressão.

    - Permite até max_words palavras (padrão 5).
    - Se a palavra final escolhida for muito curta (conjunção ou artigo), inclui a próxima palavra para dar completude.
    - Preserva pontuação final como '?' ou '!' se presente.
    """
    if not hook_raw:
        return ""
    words = hook_raw.strip().split()
    if len(words) <= max_words:
        return _trim_trailing_connectors(" ".join(words))

    chosen = words[:max_words]
    last = chosen[-1].lower().strip(".?!:,;\"'()")
    short_starters = {"e", "ou", "o", "a", "do", "da", "dos", "das", "de", "em", "no", "na", "mas"}
    if len(last) <= 2 or last in short_starters:
        # include next word if available to avoid truncated feel
        if len(words) > max_words:
            chosen.append(words[max_words])

    return _trim_trailing_connectors(" ".join(chosen))


def _trim_trailing_connectors(text: str) -> str:
    """Remove trailing articles, prepositions, and conjunctions that make a hook look incomplete.

    Repeatedly strips the last word if it's a connector, so 'RAINHA DO SAMBA E' becomes 'RAINHA DO SAMBA'.
    """
    if not text:
        return text
    connectors = {
        "E", "OU", "O", "A", "OS", "AS", "DO", "DA", "DOS", "DAS",
        "DE", "EM", "NO", "NA", "NOS", "NAS", "MAS", "COM", "POR",
        "PELO", "PELA", "QUE", "SE", "AO", "AOS", "UM", "UMA",
        "AND", "OR", "THE", "A", "AN", "OF", "IN", "ON", "AT",
        "FOR", "WITH", "BUT", "TO", "IS", "WAS", "ARE", "HER", "HIS",
    }
    words = text.strip().split()
    while len(words) > 1:
        last = re.sub(r"[^\w\u00C0-\u00FF]", "", words[-1]).upper()
        if last in connectors:
            words.pop()
        else:
            break
    return " ".join(words)


def _fix_orphan_pronoun_tail(text: str) -> str:
    """Detect and merge isolated pronoun at the end (e.g. '... DANÇANDO. ELA.') into the previous segment.

    Returns a cleaned text with the orphan pronoun merged to previous word and ensures terminal punctuation.
    """
    if not text:
        return text
    parts = text.strip().split()
    if len(parts) < 2:
        return text

    # Normalize last token (remove punctuation)
    last_raw = re.sub(r"[^\w\u00C0-\u00FF]", "", parts[-1]).upper()
    pronouns = {"ELA", "ELE", "ELAS", "ELES", "A", "O"}
    if last_raw in pronouns:
        # Merge last word into previous token
        parts[-2] = parts[-2] + " " + parts[-1]
        parts = parts[:-1]
        out = " ".join(parts).strip()
        if not re.search(r"[.!?]$", out):
            out += "."
        return out
    return text


def _ensure_headline_completeness(text: str, item: NewsItem) -> str:
    """If the generated headline/body looks like a fragment, try to extend it using available context

    Uses item.title, item.description or the start of the article text to make the phrase self-contained
    and ensures terminal punctuation. Keeps the result brief.
    """
    t = (text or "").strip()
    if not t:
        return t

    # clean last token
    tokens = t.split()
    last_token = re.sub(r"[^\w\u00C0-\u00FF]", "", tokens[-1]).upper() if tokens else ""
    short_set = {"E", "OU", "O", "A", "DO", "DA", "DOS", "DAS", "DE", "EM", "NO", "NA", "MAS", "COM", "POR", "PELO", "PELA", "ELA", "ELE"}

    looks_fragment = False
    if len(tokens) < 6:
        looks_fragment = True
    if last_token in short_set:
        looks_fragment = True
    if re.search(r"\.{2,}$", t) or t.endswith(","):
        looks_fragment = True

    if not looks_fragment:
        # ensure punctuation
        if not re.search(r"[.!?]$", t):
            if "?" in t:
                t = t + "?"
            else:
                t = t + "."
        return t

    # try to assemble a short completion from title/description/article
    title = _clean_text(item.title or "")
    desc = _clean_text(item.description or "")
    art = _extract_article_text(item.link)[:240]

    candidate = ""
    if title and title.upper() not in t.upper():
        # pick a compact variant of the title (avoid repeating full title)
        candidate = " ".join(title.split()[:10])
    elif desc:
        candidate = " ".join(desc.split()[:12])
    elif art:
        candidate = " ".join(art.split()[:12])

    if candidate:
        combined = (t + " " + candidate).strip()
        # keep it short: limit to ~22 words
        words = combined.split()
        if len(words) > 22:
            combined = " ".join(words[:22])
        if not re.search(r"[.!?]$", combined):
            combined += "."
        return combined

    # fallback: just ensure punctuation
    if not re.search(r"[.!?]$", t):
        t += "."
    return t


def _select_font() -> str:
    """Pick a bold/condensed font.

    Priority:
    1) Repo-bundled font(s) (works on GitHub Actions/Linux)
    2) System fonts (macOS/local dev)
    """
    repo_fonts = [
        ROOT_DIR / "assets" / "fonts" / "BebasNeue-Bold.ttf",
        ROOT_DIR / "assets" / "fonts" / "BebasNeue-Regular.ttf",
        ROOT_DIR / "assets" / "fonts" / "Anton-Regular.ttf",
        ROOT_DIR / "assets" / "fonts" / "Impact.ttf",
    ]
    for p in repo_fonts:
        if p.exists():
            return str(p)

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


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _ffmpeg_escape(path: str) -> str:
    return (
        path.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
    )


def _sanitize_overlay_text(text: str) -> str:
    # Remove hidden/control Unicode chars that may render as small boxes.
    # Also replaces accented characters with their non-accented counterparts for better FFmpeg compatibility.
    import unicodedata
    
    if not text:
        return ""
    
    # Converte espaços não-quebráveis (comuns em HTML) em espaços normais
    text = text.replace('\xa0', ' ')
    
    normalized = unicodedata.normalize('NFD', text)
    sanitized = "".join([c for c in normalized if unicodedata.category(c) != 'Mn'])
    
    # Mantém ASCII imprimível (32-126) E também quebras de linha (\n = 10, \r = 13)
    # Isso evita que as palavras grudem quando há quebra de linha ou espaços especiais
    sanitized = "".join([c for c in sanitized if 32 <= ord(c) <= 126 or ord(c) in (10, 13)])
    
    return sanitized.strip()


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


def _adjust_color_brightness(r: int, g: int, b: int, factor: float = 0.5) -> tuple[int, int, int]:
    """Adjust the brightness of an RGB color by a given factor."""
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return r, g, b


def _estimate_logo_bg_color(logo_path: Path) -> str:
    """Estimate a background hex color from logo border pixels and adjust brightness."""
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
        else:
            r = sum(c[0] for c in samples) // len(samples)
            g = sum(c[1] for c in samples) // len(samples)
            b = sum(c[2] for c in samples) // len(samples)

        # Adjust brightness to make the color darker
        r, g, b = _adjust_color_brightness(r, g, b, factor=0.5)
        return f"0x{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "0x202020"  # Default to a dark gray color


def _wrap_for_overlay(text: str, max_chars: int, max_lines: int, *, upper: bool = False) -> str:
    clean = _clean_text(text)
    if upper:
        clean = clean.upper()
    # Use break_long_words=False para evitar cortar palavras no meio
    wrapped = textwrap.wrap(clean, width=max_chars, break_long_words=False, break_on_hyphens=False)

    # Post-process to avoid lines that end with very short words (articles/conjunctions)
    def _fix_trailing_short_words(lines: list[str]) -> list[str]:
        short_set = {"E", "OU", "O", "A", "DO", "DA", "DOS", "DAS", "DE", "EM", "NO", "NA", "MAS", "COM", "POR", "PELO", "PELA"}
        fixed: list[str] = []
        for i, line in enumerate(lines):
            line = line.rstrip()
            # If line ends with a short word, move that word to the start of the next line
            parts = line.rsplit(" ", 1)
            if len(parts) == 2:
                last = parts[-1].strip()
                if last.upper() in short_set and i + 1 < len(lines):
                    # remove last from current line and prepend to next
                    new_curr = parts[0]
                    next_line = lines[i + 1].lstrip()
                    lines[i + 1] = f"{last} {next_line}".strip()
                    fixed.append(new_curr)
                    continue
            fixed.append(line)
        # Remove empty lines introduced by moving words
        return [ln for ln in fixed if ln]

    fixed_wrapped = _fix_trailing_short_words(wrapped)
    # Trim trailing connectors from the last visible line to avoid incomplete phrases
    if fixed_wrapped:
        fixed_wrapped[-1] = _trim_trailing_connectors(fixed_wrapped[-1])
        fixed_wrapped = [ln for ln in fixed_wrapped if ln.strip()]
    # We prioritize showing the full message without "..." suffixes
    return "\n".join(fixed_wrapped[:max_lines])


def _pick_pt_hook(headline: str) -> str:
    h = _clean_text(headline).lower()
    if any(k in h for k in ["morre", "morte", "luto", "velório", "velorio", "enterro"]):
        return random.choice(["NINGUEM ACREDITOU", "CHOCOU O BRASIL", "FIM INESPERADO"])
    if any(k in h for k in ["bbb", "big brother", "paredão", "paredao", "eliminação", "eliminacao", "prova do líder", "prova do lider", "anjo"]):
        return random.choice(["BBB PEGOU FOGO", "PASSOU DO LIMITE?", "FOI JUSTO?", "BBB EXPLODIU"])
    if any(k in h for k in ["a fazenda", "reality", "peão", "peao"]):
        return random.choice(["FOI LONGE DEMAIS?", "REALITY EXPLODIU", "PASSOU DO LIMITE?"])
    if any(k in h for k in ["filha", "filho", "bebê", "bebe", "gravidez", "grávida", "gravida", "nasceu"]):
        return random.choice(["NINGUEM ESPERAVA", "SERA VERDADE?", "CHOCOU TODO MUNDO"])
    if any(k in h for k in ["separ", "divórcio", "divorcio", "trai", "affair", "corno"]):
        return random.choice(["MERECIA ISSO?", "ERA OBVIO?", "FIM MERECIDO?"])
    if any(k in h for k in ["polêmica", "polemica", "briga", "treta", "confusão", "confusao", "desabaf"]):
        return random.choice(["QUEM TEM RAZAO?", "FOI EXAGERO?", "PASSOU DO LIMITE?"])
    if any(k in h for k in ["novela", "personagem", "ator", "atriz", "papel", "cena"]):
        return random.choice(["CONCORDAM?", "FEZ SENTIDO?", "ERA NECESSARIO?"])
    if any(k in h for k in ["cirurgia", "hospital", "internado", "internada", "saúde", "saude", "doença", "doenca"]):
        return random.choice(["NINGUEM SABIA", "SERA GRAVE?", "CHOCOU GERAL"])
    if any(k in h for k in ["namoro", "casal", "romance", "casamento", "noivar", "noivo", "noiva"]):
        return random.choice(["COMBINAM?", "VAI DURAR?", "VOCES APROVAM?"])
    if any(k in h for k in ["carnaval", "bloco", "fantasia", "desfile"]):
        return random.choice(["FOI DEMAIS?", "ARRASOU OU ERROU?", "APROVAM O LOOK?"])
    return random.choice(["VOCE CONCORDA?", "CHOCOU GERAL", "NINGUEM ESPERAVA"])


def _pick_en_hook(headline: str) -> str:
    h = _clean_text(headline).lower()
    if any(k in h for k in ["dies", "death", "dead", "passed away", "funeral"]):
        return random.choice(["NO ONE EXPECTED THIS", "GONE TOO SOON?", "SHOCKING LOSS"])
    if any(k in h for k in ["split", "divorce", "cheat", "scandal", "affair"]):
        return random.choice(["WAS IT DESERVED?", "WENT TOO FAR?", "WHO WAS WRONG?"])
    if any(k in h for k in ["baby", "pregnan", "daughter", "son", "born"]):
        return random.choice(["DID YOU EXPECT THIS?", "IS THIS REAL?", "NO ONE SAW THIS COMING"])
    if any(k in h for k in ["arrest", "jail", "court", "lawsuit", "sued"]):
        return random.choice(["DESERVED OR NOT?", "WENT TOO FAR?", "WAS IT FAIR?"])
    if any(k in h for k in ["wedding", "engaged", "dating", "romance", "couple"]):
        return random.choice(["WILL IT LAST?", "DO THEY MATCH?", "DO YOU APPROVE?"])
    return random.choice(["DO YOU AGREE?", "NO ONE EXPECTED THIS", "IS THIS RIGHT?"])


def _is_portuguese_context(source: str, headline: str) -> bool:
    # Strict check for BR portals
    if source in {"contigo", "ofuxico", "terra_gente", "ig_gente"}:
        return True
    h = _clean_text(headline).lower()
    pt_markers = [" não ", " com ", " para ", " dos ", " das ", "você", "fofoca", "famosos", " é ", " o ", " a "]
    return any(m in h for m in pt_markers)


def _build_text_layers(headline: str, source: str) -> tuple[str, str]:
    """Cria hook e resumo de fallback quando a IA não gera conteúdo adequado.
    
    O hook será uma pergunta impactante relacionada ao tema da notícia.
    """
    clean = _clean_text(headline)
    is_pt = _is_portuguese_context(source, clean)

    # Hook: pergunta temática impactante (sem forçar nome de pessoa)
    hook_text = _pick_pt_hook(clean) if is_pt else _pick_en_hook(clean)
    hook = _wrap_for_overlay(hook_text, max_chars=20, max_lines=2, upper=True)

    # Body: usa o título limpo como resumo
    summary = clean
    return hook, summary


def _headline_for_overlay(headline: str, max_chars: int = 24, max_lines: int = 5) -> str:
    # Backward-compat helper for scripts that still call this.
    return _wrap_for_overlay(headline, max_chars=max_chars, max_lines=max_lines, upper=True)


def _build_display_headline(headline: str) -> str:
    # Portal-style, bold and concise.
    # Aumentado para 28 chars por linha e 9 linhas para acomodar notícias longas sem cortar
    return _wrap_for_overlay(headline, max_chars=28, max_lines=9, upper=True)


def _summarize_news_text(item: NewsItem) -> str:
    is_pt = any(profile_name in item.feed_url for profile_name, _ in FEED_PROFILES["br"]) or "contigo" in item.feed_url or "ofuxico" in item.feed_url or "terra" in item.feed_url or "ig" in item.feed_url
    
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
                    "Voce e um roteirista profissional de Shorts/Reels de fofoca brasileira especializado em viralizacao.\n\n"

                    "FORMATO OBRIGATORIO — exatamente 5 linhas de TEXTO PURO, nada antes e nada depois:\n\n"

                    "Linha 1 = HOOK (ACAO IMEDIATA): Descreva o evento principal com VERBO FORTE + QUEM + O QUE. Maximo 8 palavras. TUDO EM CAPS.\n"
                    "Linha 2 = FATO DIRETO: O que aconteceu de forma objetiva e curta.\n"
                    "Linha 3 = REACAO: Como a web, participantes ou envolvidos reagiram.\n"
                    "Linha 4 = IMPACTO: Consequencia imediata no jogo, narrativa ou relacao.\n"
                    "Linha 5 = PERGUNTA POLARIZADA: Pergunta que obriga o espectador a escolher um lado.\n\n"

                    "REGRAS DE OURO PARA HOOKS:\n"
                    "- O HOOK deve ser uma FRASE COMPLETA sobre o evento principal da noticia.\n"
                    "- Comece com VERBO DE ACAO forte (CHOCOU, REVELOU, EXPLODIU, DESABAFOU, ATACOU, BEIJOU, FLAGROU, etc).\n"
                    "- Exemplo BOM: 'BRUNA MARQUEZINE FLAGRADA COM NOVO AFFAIR'\n"
                    "- Exemplo BOM: 'PARTICIPANTE EXPULSO APOS BRIGA NO BBB'\n"
                    "- Exemplo RUIM: 'VOCE DESPREZA O CARNAVAL E DECIDE' (generico, nao fala do evento real)\n"
                    "- NUNCA comece com 'VOCE', 'O QUE', 'VEJA', 'CONHECE'.\n"
                    "- Evite palavras vagas como 'clima', 'situacao', 'momento', 'algo por tras'.\n"
                    "- O hook SEMPRE deve dizer QUEM fez O QUE de forma especifica.\n"
                    "- Linhas 2, 3 e 4 devem seguir exatamente: Fato -> Reacao -> Impacto. Sem contexto longo.\n"
                    "- Linguagem direta, ritmo rapido, frases curtas.\n"
                    "- ZERO hashtags.\n"
                    "- ZERO emojis.\n"
                    "- TODAS AS LINHAS EM CAPS LOCK.\n\n"

                    "Responda APENAS com as 5 linhas. Nada mais."
                )
                user_content = f"Noticia:\n{context}"
            else:
                system_instr = (
                    "You are a Shorts/Reels gossip scriptwriter specialized in viral content.\n\n"
                    "MANDATORY FORMAT — exactly 5 lines of plain text, nothing else:\n\n"
                    "Line 1 = HOOK (IMMEDIATE ACTION): Describe the main event with STRONG VERB + WHO + WHAT. Max 8 words.\n"
                    "Line 2 = DIRECT FACT: What happened objectively.\n"
                    "Line 3 = REACTION: How the web/house reacted.\n"
                    "Line 4 = IMPACT: The immediate consequence or narrative shift.\n"
                    "Line 5 = POLARIZED QUESTION: A question that forces the viewer to take a stand.\n\n"
                    "GOLDEN RULES FOR HOOKS:\n"
                    "- HOOK must be a COMPLETE PHRASE about the actual news event.\n"
                    "- Start with STRONG ACTION VERB (SHOCKED, REVEALED, EXPLODED, ATTACKED, CAUGHT, KISSED, etc).\n"
                    "- Example GOOD: 'BRUNA MARQUEZINE CAUGHT WITH NEW AFFAIR'\n"
                    "- Example GOOD: 'CONTESTANT EXPELLED AFTER BBB FIGHT'\n"
                    "- Example BAD: 'YOU DESPISE CARNIVAL AND DECIDE' (generic, not about the real event)\n"
                    "- NEVER start with 'YOU', 'WHAT', 'SEE', 'CHECK'.\n"
                    "- Avoid vague words like 'vibe', 'situation', 'moment', 'something behind'.\n"
                    "- Hook ALWAYS says WHO did WHAT specifically.\n"
                    "- BODY (Lines 2, 3, 4) follows: Fact -> Reaction -> Impact. No fluff.\n"
                    "- FINAL QUESTION must be polarized.\n"
                    "- ALL CAPS, zero hashtags, zero emojis.\n\n"
                    "Respond ONLY with the 5 lines. Nothing before, nothing after."
                )
                user_content = f"News:\n{context}"

            payload = {
                "model": cfg.model,
                "temperature": 0.7,
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
                    # Preserve newlines — the parser needs them to split hook/body/question
                    return str(content).strip()
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

    # Palette of colors used to vary background and tarjas per publication.
    # Deterministic selection based on headline content (so each publication keeps the same color).
    PALETTE = [
        "0x1A73E8",  # blue
        "0xFB8C00",  # orange
        "0x06B6D4",  # cyan
        "0x8B5CF6",  # purple
        "0x16A34A",  # green
        "0xEF4444",  # red
        "0xF59E0B",  # amber
        "0xE11D48",  # rose
    ]

    # We'll pick a color based on the main headline text so it's repeatable per post.
    # main_input is computed below; use a temporary seed from the headline file if needed.
    # Default to black on error.
    bg_color = "0x000000"
    tarja_color = "0x000000"

    # Make spacing consistent across macOS/Linux builds of FFmpeg/libfreetype.
    # Keep only widely-supported drawtext params.

    SAFE_TOP = 220
    SAFE_BOTTOM = 1520

    main_path = summary_file or headline_file
    main_raw = main_path.read_text(encoding="utf-8") if main_path.exists() else ""
    main_clean = _sanitize_overlay_text(main_raw).replace("\xa0", " ")
    
    hook_raw = hook_file.read_text(encoding="utf-8") if hook_file and hook_file.exists() else ""
    hook_clean = _sanitize_overlay_text(hook_raw).replace("\xa0", " ")

    # Render HOOK - 2 linhas max, 20 chars por linha
    hook_lines = textwrap.wrap(hook_clean, width=20, break_long_words=False, break_on_hyphens=False)[:2]
    hook_filters = []

    # Keep hook on tarja, but inside safe area.
    hook_base_y = _clamp(560, SAFE_TOP, SAFE_BOTTOM)
    for i, line in enumerate(hook_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = _clamp(hook_base_y + (i * 104), SAFE_TOP, SAFE_BOTTOM)
        hook_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize=85:fix_bounds=1:"
            f"borderw=3:bordercolor=black:"
            f"box=1:boxcolor={hook_box_color}@0.96:boxborderw=18:"
            f"x=(w-tw)/2:y={y_pos}"
        )

    # Render MAIN HEADLINE
    main_input = " ".join(main_clean.split())
    
    # Remove reticências automáticas que cortam frases
    # Se o texto termina com "...", remove para não dar impressão de corte artificial
    if main_input.endswith("..."):
        main_input = main_input[:-3].rstrip()
    
    # Quebra em linhas com mais caracteres por linha para evitar cortes
    # Aumentado de width=28 para width=32 e limite de 9 para 10 linhas
    main_lines = textwrap.wrap(main_input, width=32, break_long_words=False, break_on_hyphens=False)[:10]
    main_filters = []

    # Ajuste dinâmico de fonte para textos muito longos (até 10 linhas)
    if len(main_lines) > 7:
        line_spacing = 65
        font_size = 54
    elif len(main_lines) > 5:
        line_spacing = 72
        font_size = 60
    else:
        line_spacing = 82
        font_size = 68

    # Start Y so that the full block ends at SAFE_BOTTOM.
    block_h = max(0, (len(main_lines) - 1) * line_spacing)
    start_y = _clamp(SAFE_BOTTOM - block_h, SAFE_TOP + 520, SAFE_BOTTOM)

    for i, line in enumerate(main_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = _clamp(start_y + (i * line_spacing), SAFE_TOP, SAFE_BOTTOM)
        main_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize={font_size}:fix_bounds=1:"
            f"borderw=3:bordercolor=black:"
            f"x=(w-tw)/2:y={y_pos}"
        )

    vf_layers = [
        "scale=1080:-2",  # Ajusta o vídeo para caber no quadro 9:16
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",  # Adiciona padding para manter a proporção
        "setsar=1",  # Garante pixels quadrados
        "format=yuv420p",  # Formato de saída correto
        "eq=brightness=-0.02:contrast=1.08:saturation=1.02",  # Ajustes de cor
        *hook_filters,  # Filtros para o texto do hook
        *main_filters,  # Filtros para o texto principal
        f"drawtext=text='{cta_escaped}':fontfile='{font}':fontcolor=white@0.88:"
        f"borderw=2:bordercolor=black:"
        "fontsize=53:x=(w-text_w)/2:y=h*0.90:enable='lt(mod(t\\,1.4)\\,0.7)'",  # CTA piscante
    ]
    vf = ",".join(vf_layers)

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


def _render_short_video(
    video_path: Path,
    headline_file: Path,
    source: str,
    out_video: Path,
    *,
    hook_file: Path | None = None,
    summary_file: Path | None = None,
    cta_text: str = "INSCREVA-SE",
    logo_path: Path | None = None,
    duration_s: float = 20.0,
) -> None:
    """Renderiza um post de fofoca usando um vídeo como base ao invés de imagem estática.
    Corta o vídeo em `duration_s` segundos (default 20s).
    """
    ff = ensure_ffmpeg("tools")
    font = _ffmpeg_escape(_select_font())
    
    fade_out_start = max(0.0, duration_s - 1.2)
    cta_escaped = _ffmpeg_escape_text(cta_text.upper())
    hook_box_color = "0x000000"

    PALETTE = [
        "0x1A73E8",  # blue
        "0xFB8C00",  # orange
        "0x06B6D4",  # cyan
        "0x8B5CF6",  # purple
        "0x16A34A",  # green
        "0xEF4444",  # red
        "0xF59E0B",  # amber
        "0xE11D48",  # rose
    ]

    SAFE_TOP = 220
    SAFE_BOTTOM = 1520

    main_path = summary_file or headline_file
    main_raw = main_path.read_text(encoding="utf-8") if main_path.exists() else ""
    main_clean = _sanitize_overlay_text(main_raw).replace("\xa0", " ")
    
    hook_raw = hook_file.read_text(encoding="utf-8") if hook_file and hook_file.exists() else ""
    hook_clean = _sanitize_overlay_text(hook_raw).replace("\xa0", " ")

    # Render HOOK
    hook_lines = textwrap.wrap(hook_clean, width=20, break_long_words=False, break_on_hyphens=False)[:2]
    hook_filters = []

    hook_base_y = _clamp(560, SAFE_TOP, SAFE_BOTTOM)
    for i, line in enumerate(hook_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = _clamp(hook_base_y + (i * 104), SAFE_TOP, SAFE_BOTTOM)
        hook_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize=85:fix_bounds=1:"
            f"borderw=3:bordercolor=black:"
            f"box=1:boxcolor={hook_box_color}@0.96:boxborderw=18:"
            f"x=(w-tw)/2:y={y_pos}"
        )

    # Render MAIN HEADLINE
    main_input = " ".join(main_clean.split())
    
    # Remove reticências automáticas que cortam frases
    # Se o texto termina com "...", remove para não dar impressão de corte artificial
    if main_input.endswith("..."):
        main_input = main_input[:-3].rstrip()
    
    # Seleciona cores determinísticas baseadas no texto
    try:
        seed_text = main_input or headline_file.read_text(encoding="utf-8")
        h = hashlib.sha1(seed_text.encode("utf-8")).hexdigest()
        idx = int(h, 16) % len(PALETTE)
        bg_color = PALETTE[idx]
        tarja_color = PALETTE[(idx + 3) % len(PALETTE)]
    except Exception:
        bg_color = "0x000000"
        tarja_color = "0x000000"
    
    # Quebra em linhas com mais caracteres por linha para evitar cortes
    # Aumentado de width=28 para width=32 e limite de 9 para 10 linhas
    main_lines = textwrap.wrap(main_input, width=32, break_long_words=False, break_on_hyphens=False)[:10]
    main_filters = []

    if len(main_lines) > 7:
        line_spacing = 65
        font_size = 54
    elif len(main_lines) > 5:
        line_spacing = 72
        font_size = 60
    else:
        line_spacing = 82
        font_size = 68

    block_h = max(0, (len(main_lines) - 1) * line_spacing)
    start_y = _clamp(SAFE_BOTTOM - block_h, SAFE_TOP + 520, SAFE_BOTTOM)

    for i, line in enumerate(main_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = _clamp(start_y + (i * line_spacing), SAFE_TOP, SAFE_BOTTOM)
        main_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize={font_size}:fix_bounds=1:"
            f"borderw=3:bordercolor=black:"
            f"x=(w-tw)/2:y={y_pos}"
        )

    # Filtros de escala e padding (serão aplicados de forma diferente com ou sem logo)
    scale_filters = [
        "scale=1080:-2",  # Escala mantendo aspect ratio
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",  # Padding preto
        "setsar=1",  # Garante pixels quadrados
        "format=yuv420p",  # Formato de saída
        "eq=brightness=-0.02:contrast=1.08:saturation=1.02",  # Ajustes de cor
    ]
    
    # Filtros de texto apenas (sem escala/pad quando há logo)
    text_filters = [
        *hook_filters,  # Filtros para o texto do hook
        *main_filters,  # Filtros para o texto principal
        f"drawtext=text='{cta_escaped}':fontfile='{font}':fontcolor=white@0.88:"
        f"borderw=2:bordercolor=black:"
        "fontsize=53:x=(w-text_w)/2:y=h*0.90:enable='lt(mod(t\\,1.4)\\,0.7)'",  # CTA piscante
    ]

    out_video.parent.mkdir(parents=True, exist_ok=True)

    if logo_path is not None and logo_path.exists():
        # Com logo: aplica scale/pad no filter_complex, depois texto
        base_filters = ",".join(scale_filters)
        text_only = ",".join(text_filters)
        args = [
            "-hide_banner",
            "-y",
            "-t",
            str(int(duration_s)),
            "-i",
            str(video_path),
            "-i",
            str(logo_path),
            "-filter_complex",
            # Escala vídeo base para 1080x1920 com aspect ratio preservado
            f"[0:v]{base_filters},{text_only}[bg];"
            # Escala logo separadamente com sin wave, mantendo proporção
            "[1:v]scale='min(360,iw)':-1:eval=frame[logo];"
            # Overlay logo no topo
            "[bg][logo]overlay=(W-w)/2:36[v]",
            "-map",
            "[v]",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_video),
        ]
    else:
        # Sem logo: aplica tudo junto no vf
        vf = ",".join(scale_filters + text_filters)
        args = [
            "-hide_banner",
            "-y",
            "-t",
            str(int(duration_s)),
            "-i",
            str(video_path),
            "-vf",
            vf,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
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

        # ── Parse da IA: espera exatamente 5 linhas (gancho / fato / reacao / impacto / pergunta) ──
        raw_script = _summarize_news_text(item)
        all_lines = [ln.rstrip() for ln in raw_script.splitlines()]

        # Separa hashtags residuais (caso a IA insira mesmo assim)
        hashtags = " ".join([ln.lower() for ln in all_lines if ln.strip().startswith("#")])

        # Limpa: remove hashtags, labels ("Variante 1", "Variation 1", etc.), linhas vazias e separadores
        content_lines: list[str] = []
        for ln in all_lines:
            stripped = ln.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if re.match(r"^-{2,}$", stripped):
                continue
            if re.match(r"^(variante|variation|vers[ãa]o|version|op[çc][ãa]o|option)\s*\d*\s*[:\-–—]*\s*", stripped, flags=re.I):
                continue
            # Remove labels inline como "Gancho:", "Hook:", "Corpo:", "Body:", "Pergunta:", "Question:", "CTA:"
            cleaned = re.sub(r"^(gancho|hook|corpo|body|pergunta|question|cta|linha|line)\s*\d*\s*[:\-–—=]\s*", "", stripped, flags=re.I).strip()
            if cleaned:
                content_lines.append(cleaned)

        # Se a IA devolveu múltiplas variações separadas por '---', pega só a primeira
        # (as content_lines já removeram '---', mas podem ter linhas de múltiplas variações)
        # ── Parsing the high-performance 5-line structure ──
        if len(content_lines) >= 5:
            hook = content_lines[0]
            # Combine Fact + Reaction + Impact into body
            body = f"{content_lines[1]} {content_lines[2]} {content_lines[3]}"
            question = content_lines[4]
            headline_text = f"{body} {question}"
        elif len(content_lines) == 4:
            hook = content_lines[0]
            body = f"{content_lines[1]} {content_lines[2]}"
            question = content_lines[3]
            headline_text = f"{body} {question}"
        elif len(content_lines) == 3:
            hook = content_lines[0]
            body = content_lines[1]
            question = content_lines[2]
            headline_text = f"{body} {question}"
        elif len(content_lines) == 2:
            hook = content_lines[0]
            headline_text = content_lines[1]
        elif len(content_lines) == 1:
            # Fallback: IA devolveu tudo em 1 linha, usa fallback completo
            hook, headline_text = _build_text_layers(item.title, item.source)
        else:
            # Fallback completo: IA não devolveu nada útil
            hook, headline_text = _build_text_layers(item.title, item.source)

        # ── Limpeza leve (sem truncamento agressivo) ──
        # Remove hashtags residuais e caracteres problemáticos, preserva pontuação
        hook_clean = re.sub(r'#\w+', '', hook).strip()
        hook_clean = re.sub(r"[^\w\s\u00C0-\u00FF?!]", '', hook_clean)
        hook_clean = re.sub(r'\s+', ' ', hook_clean).strip()
        # Garante que o hook não termina em palavra conectora (artigo/preposição/conjunção)
        hook_clean = _trim_trailing_connectors(hook_clean)

        headline_text_clean = re.sub(r'#\w+', '', headline_text).strip()
        headline_text_clean = re.sub(r'[^\w\s\u00C0-\u00FF.,!?]', '', headline_text_clean)
        headline_text_clean = re.sub(r'\s+', ' ', headline_text_clean).strip()

        # Garante pontuação final para sensação de completude
        if headline_text_clean and not re.search(r"[.!?]$", headline_text_clean):
            headline_text_clean += "?"  if "?" in headline_text else "."

        # Força caixa alta
        headline_text_clean = headline_text_clean.upper()
        
        # Hook: 20 chars por linha, máximo 2 linhas
        hook_wrapped = _wrap_for_overlay(hook_clean, max_chars=20, max_lines=2, upper=True)
        
        hook_file = post_dir / "hook.txt"
        hook_file.write_text(_sanitize_overlay_text(hook_wrapped) + "\n", encoding="utf-8")

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

        # Caption com hashtags (para redes sociais)
        # Usa hook_clean e headline_text_clean (sem hashtags inline) + hashtags separadas no final
        (post_dir / "caption.txt").write_text(
            f"{hook_clean}\n{headline_text_clean}\n\n{hashtags}\n\nFonte: {item.source.upper()}\nLink: {item.link}\n",
            encoding="utf-8",
        )

        slug = _make_slug(item.title)
        output_video = post_dir / "output" / f"gossip_{slug}.mp4"

        # ── CTA: SEMPRE usa variações da lista predefinida ──
        # Usa o título como seed para ter consistência (mesmo post = mesmo CTA)
        cta_text = _get_random_cta(item.title)
        
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

        # Adiciona um pequeno delay para garantir que o arquivo de vídeo seja liberado pelo SO
        import time
        time.sleep(1)

        # Telegram Notification with hashtags in caption
        # Clean up hook and headline for better formatting (já estão limpos, sem hashtags)
        hook_telegram = " ".join(hook_clean.split())  # Remove extra spaces/newlines
        headline_telegram = " ".join(headline_text_clean.split())  # Single line
        
        telegram_caption = (
            f"🔥 {hook_telegram}\n\n"
            f"{headline_telegram}\n\n"
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
    p.add_argument("--url", default="", help="Direct link to a news article.")
    p.add_argument("--logo", default="", help="Optional logo path (png/webp/jpg).")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    
    if args.url:
        print(f"🔗 Processando URL direta: {args.url}")
        # Tenta identificar a fonte pelo domínio
        source = "custom"
        for name, _ in FEED_PROFILES["br"] + FEED_PROFILES["intl"]:
            if name in args.url:
                source = name
                break
        item = _fetch_news_from_url(args.url, source)
    else:
        feeds = FEED_PROFILES[args.profile]
        item = _fetch_first_news(feeds)
    
    if item:
        create_post_for_item(item, args)


if __name__ == "__main__":
    main()
