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
# Baseados nos posts de maior performance do canal:
# - "COMENTA O QUE ACHOU!" (engajamento direto, Post Travadinha)
# - "SALVA ESSE POST" (bookmark, Post Ana Paula)
# - "CURTE SE GOSTA DE EMOCAO NO BBB" (condicional, Post Babu)
CTA_VARIATIONS_GENERIC = [
    "COMENTA O QUE ACHOU!",
    "SALVA ESSE POST",
    "MARCA QUEM PRECISA VER ISSO",
    "COMENTA SUA OPINIAO!",
    "SEGUE PRA NAO PERDER NADA",
    "CONTA NOS COMENTARIOS!",
    "MANDA PRO AMIGO QUE AMA FOFOCA",
    "SALVA E MANDA PRA ALGUEM",
]

# CTAs temáticos - selecionados automaticamente por contexto da notícia
CTA_BY_THEME = {
    "bbb": [
        "CURTE SE GOSTA DE EMOCAO NO BBB",
        "COMENTA QUEM VOCE APOIA!",
        "SALVA PRA ACOMPANHAR O BBB",
        "QUEM MERECE SAIR? COMENTA!",
        "CURTE SE CONCORDA!",
    ],
    "separacao": [
        "COMENTA SE JA SABIA!",
        "ACHA QUE VOLTA? COMENTA!",
        "CURTE SE FICOU CHOCADO!",
        "COMENTA O QUE ACHOU!",
    ],
    "namoro": [
        "COMENTA SE SHIPPA!",
        "COMBINAM? COMENTA!",
        "CURTE SE APROVA O CASAL!",
        "COMENTA O QUE ACHOU!",
    ],
    "morte": [
        "SALVA ESSE POST",
        "DEIXA SEU COMENTARIO",
        "MANDA FORCA NOS COMENTARIOS",
    ],
    "treta": [
        "QUEM TEM RAZAO? COMENTA!",
        "CURTE SE FICOU CHOCADO!",
        "COMENTA SUA OPINIAO!",
        "FOI JUSTO? COMENTA!",
    ],
    "carnaval": [
        "COMENTA O QUE ACHOU!",
        "CURTE SE AMOU O LOOK!",
        "ARRASOU OU ERROU? COMENTA!",
        "MANDA PRA QUEM AMA CARNAVAL",
    ],
    "gravidez": [
        "COMENTA SE JA SABIA!",
        "CURTE PRA DESEJAR FELICIDADES!",
        "SALVA ESSE POST",
    ],
    "policia": [
        "CURTE SE FICOU CHOCADO!",
        "COMENTA O QUE ACHOU!",
        "SALVA ESSE POST",
    ],
}

HOOK_HISTORY_FILE = "hook_history.json"
HOOK_HISTORY_WINDOW = 12
HOOK_HISTORY_MAX = 120

# Estruturas com maior risco de parecer "reused/inauthentic" quando repetidas em sequência.
HOOK_REPEAT_MARKERS_PT = [
    "VIROU TRETA",
    "REAGE ASSIM",
    "NINGUEM ESPERAVA",
    "MEXEU COM A WEB",
    "CHOCOU A WEB",
    "PEGOU FOGO",
    "DEU O QUE FALAR",
    "SURGE COM NOVA",
]
HOOK_REPEAT_MARKERS_EN = [
    "TURNED INTO DRAMA",
    "NOBODY EXPECTED",
    "SHOCKED THE INTERNET",
    "REACTS LIKE THIS",
    "WENT VIRAL",
]


def _detect_news_theme(headline: str) -> str:
    """Detecta o tema da notícia para selecionar CTA e hook adequados."""
    h = headline.lower()
    if any(k in h for k in ["bbb", "big brother", "paredão", "paredao", "eliminação", "eliminacao",
                             "prova do líder", "prova do lider", "anjo", "confinamento"]):
        return "bbb"
    if any(k in h for k in ["morre", "morte", "luto", "velório", "velorio", "enterro", "falece"]):
        return "morte"
    if any(k in h for k in ["separ", "divórcio", "divorcio", "trai", "affair", "corno", "termina"]):
        return "separacao"
    if any(k in h for k in ["namoro", "casal", "romance", "casamento", "noivar", "noivo", "noiva",
                             "juntinhos", "flagrad", "beij"]):
        return "namoro"
    if any(k in h for k in ["polêmica", "polemica", "briga", "treta", "confusão", "confusao",
                             "desabaf", "atac", "xing", "vingança", "vinganca"]):
        return "treta"
    if any(k in h for k in ["carnaval", "bloco", "fantasia", "desfile", "abadá", "abada"]):
        return "carnaval"
    if any(k in h for k in ["filha", "filho", "bebê", "bebe", "gravidez", "grávida", "gravida", "nasceu"]):
        return "gravidez"
    if any(k in h for k in ["pres", "detenção", "detencao", "cadeia", "processo", "policia", "policial"]):
        return "policia"
    return "generic"


def _get_random_cta(seed_text: str = "", headline: str = "") -> str:
    """Seleciona um CTA temático de forma determinística baseado no seed_text.
    
    Usa o tema da notícia para escolher CTAs mais relevantes (padrão dos posts top).
    Se seed_text for fornecido, o mesmo texto sempre retorna o mesmo CTA.
    """
    if headline == "generic":
        theme = "generic"
    else:
        theme = _detect_news_theme(headline or seed_text)
    
    # Pega CTAs do tema ou genéricos
    cta_pool = CTA_BY_THEME.get(theme, CTA_VARIATIONS_GENERIC)
    
    if seed_text:
        hash_value = int(hashlib.md5(seed_text.encode()).hexdigest(), 16)
        random.seed(hash_value)
    
    cta = random.choice(cta_pool)
    
    # Reset random seed para não afetar outros randoms
    random.seed()
    
    return cta


def _sanitize_cta_text(cta: str) -> str:
    """Remove emoji/symbol chars that often render as tofu (a square with X) in FFmpeg drawtext."""
    t = _clean_text(cta)
    # Keep latin letters (incl. accents), digits, spaces and common punctuation.
    # This intentionally removes arrows/emojis like 👇 🔥 🔔 etc.
    t = re.sub(r"[^\w\s\u00C0-\u00FF.,!?\-–—'\"()\[\]/\\+&:#@]", "", t)
    return _clean_text(t)


def _truncate_at_sentence_boundary(text: str, *, max_chars: int = 220) -> str:
    """Truncate without cutting the last phrase in the middle.

    Prefers '.', '!' or '?' boundaries. Falls back to ',', ';', ':' and finally last-space + '...'.
    """
    t = _clean_text(text)
    if len(t) <= max_chars:
        return t

    cand = t[:max_chars].rstrip()

    for sep in ("?", "!", "."):
        idx = cand.rfind(sep)
        if idx >= int(max_chars * 0.55):
            return cand[: idx + 1].strip()

    for sep in (";", ",", ":"):
        idx = cand.rfind(sep)
        if idx >= int(max_chars * 0.65):
            return cand[: idx + 1].strip()

    cut = cand.rsplit(" ", 1)[0].strip()
    return (cut + "...") if cut else (cand + "...")


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
        match = re.search(pattern, html or "", re.IGNORECASE)
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


def _fetch_first_news(feeds: list[tuple[str, str]], skip_titles: list[str] | None = None) -> NewsItem:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GossipPostBot/1.0)"}
    skip_titles = skip_titles or []

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
                if title in skip_titles:
                    continue
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
            if title in skip_titles:
                continue
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
    """Remove trailing connectors/articles that make hooks look cut off."""
    if not text:
        return text
    connectors = {
        "E", "OU", "O", "A", "OS", "AS", "UM", "UMA", "UNS", "UMAS",
        "DE", "DO", "DA", "DOS", "DAS", "NO", "NA", "NOS", "NAS",
        "EM", "COM", "POR", "PARA", "PELO", "PELA", "SEM",
        "THE", "A", "AN", "OF", "TO", "IN", "ON", "AT", "FOR", "WITH", "AND", "OR",
    }

    words = [w for w in text.split() if w]
    while words:
        last_clean = re.sub(r"[^\w\u00C0-\u00FF]", "", words[-1]).upper()
        if not last_clean:
            words.pop()
            continue
        if last_clean in connectors:
            words.pop()
            continue
        break
    return " ".join(words).strip()


def _fit_hook_to_overlay(hook: str, *, max_chars: int = 24, max_lines: int = 2, min_words: int = 6) -> str:
    """Fit hook into overlay without truncating in awkward places."""
    words = [w for w in _clean_text(hook).split() if w]
    if not words:
        return ""

    def _wrap_count(text: str) -> int:
        return len(textwrap.wrap(text, width=max_chars, break_long_words=False, break_on_hyphens=False))

    candidate_words = words[:]
    candidate = _trim_trailing_connectors(" ".join(candidate_words))
    while _wrap_count(candidate) > max_lines and len(candidate_words) > min_words:
        candidate_words.pop()
        candidate = _trim_trailing_connectors(" ".join(candidate_words))

    # Last-resort hard cap to avoid line clipping by _wrap_for_overlay.
    if _wrap_count(candidate) > max_lines:
        budget = max_chars * max_lines
        picked: list[str] = []
        used = 0
        for w in candidate_words:
            add = len(w) + (1 if picked else 0)
            if used + add > budget:
                break
            picked.append(w)
            used += add
        candidate = _trim_trailing_connectors(" ".join(picked))

    return candidate.strip()


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


def _fix_web_fragment(text: str) -> str:
    """Fix fragment endings like '... A WEB.' which feel truncated in PT-BR overlays."""
    if not text:
        return text
    t = re.sub(r"\s+", " ", text.strip())

    # If ends with 'A WEB.' or 'A WEB' with no verb, complete it.
    if re.search(r"\bA WEB\b\s*\.?$", t, flags=re.I):
        # If there's already a 'A WEB' reaction earlier, just drop the tail.
        # Example: '... A WEB PIRÔU ... A WEB.' -> remove last fragment.
        t = re.sub(r"(\bA WEB\b)\s*\.?$", "A WEB REAGIU.", t, flags=re.I)
        return t

    # Also handle '.. A WEB.'
    if re.search(r"\.\.\s*A WEB\s*\.?$", t, flags=re.I):
        t = re.sub(r"\.\.\s*A WEB\s*\.?$", ".. A WEB REAGIU.", t, flags=re.I)
        return t

    return t


def _polish_body_punctuation(text: str) -> str:
    """Normalize punctuation artifacts produced by model rewrites."""
    if not text:
        return text
    t = re.sub(r"\s+", " ", text.strip())
    # Remove comma before period/exclamation/question.
    t = re.sub(r",\s*([.!?])", r"\1", t)
    # Remove duplicated commas.
    t = re.sub(r",\s*,+", ", ", t)
    # Avoid ending with a dangling comma.
    t = re.sub(r",\s*$", "", t)
    # Avoid abrupt pronoun+verb tails (e.g., '... ELA DISSE.').
    t = re.sub(r"\b(ELA|ELE)\s+DISSE\s*\.?$", r"\1 DISSE TUDO.", t, flags=re.I)
    return t


def _is_probably_bad_hook(text: str) -> bool:
    t = _clean_text(text).upper()
    if not t:
        return True
    if t.startswith(("CONTEXTO", "CONTEXT", "SEGUNDO FAS", "ACCORDING TO FANS", "A REPERCUSSAO", "THE BACKLASH")):
        return True
    if re.search(r"\b(LINHA|LINE)\s*\d+\b", t):
        return True
    words = [w for w in t.split() if w]
    return len(words) < 5


def _is_bad_overlay_body(text: str) -> bool:
    t = _clean_text(text)
    if not t:
        return True
    # Placeholder labels and common broken endings seen in scheduler outputs.
    if re.search(r"\b(CONTEXTO|CONTEXT)\s*:", t, flags=re.I):
        return True
    if re.search(r"\b(SEGUNDO\s+F[ÃA]S|ACCORDING TO FANS)\b.{0,40}\b(FOI|WAS)\.?\s*$", t, flags=re.I):
        return True
    if re.search(r"\bA\s+WEB\s+FOI\.?\s*$", t, flags=re.I):
        return True
    if re.search(r"\b(FOI|WAS)\.?\s*$", t, flags=re.I) and len(t.split()) <= 24:
        return True
    return False


def _is_valid_ai_cta(text: str) -> bool:
    t = _clean_text(text).upper()
    if not t:
        return False
    if len(t) < 6 or len(t) > 45:
        return False
    # Question-style closing line is not a CTA for this template.
    if "?" in t:
        return False
    if t.startswith(("ISSO E ", "EXAGERO OU", "AVANCO OU", "WHAT ", "IS THIS ", "DO YOU ")):
        return False
    return bool(re.search(r"\b(COMENTA|CURTE|SALVA|SEGUE|MARCA|MANDA|CONTA)\b", t, flags=re.I))


def _normalize_hook_text(text: str) -> str:
    import unicodedata

    base = unicodedata.normalize("NFKD", (text or "")).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^\w\s]", " ", base.upper())
    return re.sub(r"\s+", " ", base).strip()


def _load_recent_hook_history(history_path: Path, *, window: int = HOOK_HISTORY_WINDOW) -> list[str]:
    if not history_path.exists():
        return []
    try:
        raw = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    hooks = raw.get("hooks") if isinstance(raw, dict) else None
    if not isinstance(hooks, list):
        return []

    recent: list[str] = []
    for entry in hooks[-window:]:
        if isinstance(entry, dict):
            h = _normalize_hook_text(str(entry.get("hook") or ""))
            if h:
                recent.append(h)
    return recent


def _save_hook_to_history(history_path: Path, hook_text: str, *, title: str = "", source: str = "") -> None:
    payload: dict[str, object]
    hooks: list[dict[str, str]]
    if history_path.exists():
        try:
            payload = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {"version": 1, "hooks": []}
    else:
        payload = {"version": 1, "hooks": []}

    existing = payload.get("hooks")
    hooks = existing if isinstance(existing, list) else []
    hooks.append(
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "hook": hook_text,
            "normalized": _normalize_hook_text(hook_text),
            "title": _clean_text(title),
            "source": _clean_text(source),
        }
    )
    payload["hooks"] = hooks[-HOOK_HISTORY_MAX:]
    history_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _hook_has_repeated_marker(candidate: str, recent_hooks: list[str], *, is_pt: bool) -> bool:
    c = _normalize_hook_text(candidate)
    if not c:
        return False

    if c in set(recent_hooks):
        return True

    markers = HOOK_REPEAT_MARKERS_PT if is_pt else HOOK_REPEAT_MARKERS_EN
    for marker in markers:
        m = _normalize_hook_text(marker)
        if m in c and any(m in rh for rh in recent_hooks):
            return True
    return False


def _diversify_hook_if_reused(hook: str, *, headline: str, source: str, recent_hooks: list[str]) -> str:
    is_pt = _is_portuguese_context(source, headline)
    candidate = hook

    for _ in range(4):
        if not _hook_has_repeated_marker(candidate, recent_hooks, is_pt=is_pt):
            return candidate
        replacement = _pick_pt_hook(headline) if is_pt else _pick_en_hook(headline)
        replacement = _fit_hook_to_overlay(replacement, max_chars=24, max_lines=2, min_words=6)
        candidate = _trim_trailing_connectors(replacement)

    return candidate


def _ensure_headline_completeness(text: str, item: NewsItem) -> str:
    """If the generated headline/body looks like a fragment, try to extend it using available context.

    Uses item.title, item.description or the start of the article text to make the phrase self-contained.
    """
    t = (text or "").strip()
    if not t:
        return t

    # clean last token
    tokens = t.split()
    last_token = re.sub(r"[^\w\u00C0-\u00FF]", "", tokens[-1]).upper() if tokens else ""
    short_set = {"E", "OU", "O", "A", "DO", "DA", "DOS", "DAS", "DE", "EM", "NO", "NA", "MAS", "COM", "POR", "PELO", "PELA", "ELA", "ELE", "QUE"}

    looks_fragment = False
    if len(tokens) < 6:
        looks_fragment = True
    if last_token in short_set:
        looks_fragment = True
    if re.search(r"\.{2,}$", t) or t.endswith(","):
        looks_fragment = True

    # Special-case: ends with a dangling named-entity only (e.g. '... DISSE QUE BABU.')
    if re.search(r"\bDISSE\s+QUE\s+[A-ZÀ-Ü]{2,}\.?$", t, flags=re.I):
        looks_fragment = True

    if not looks_fragment:
        if not re.search(r"[.!?]$", t):
            t += "?" if "?" in t else "."
        return t

    # If we have a typical dangling pattern, prefer a short closure instead of appending random words
    if re.search(r"\bDISSE\s+QUE\b\s*[A-ZÀ-Ü]{2,}\.?$", t, flags=re.I):
        t = re.sub(r"\bDISSE\s+QUE\s+[A-ZÀ-Ü]{2,}\.?$", "DISSE TUDO.", t, flags=re.I).strip()
        if not re.search(r"[.!?]$", t):
            t += "."
        return t

    # try to assemble a short completion from title/description/article
    title = _clean_text(item.title or "")
    desc = _clean_text(item.description or "")
    art = _extract_article_text(item.link)[:240]

    candidate = ""
    if title and title.upper() not in t.upper():
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

        # Avoid ending on connectors / too-short last token
        end_tokens = combined.split()
        if end_tokens:
            end_last = re.sub(r"[^\w\u00C0-\u00FF]", "", end_tokens[-1]).upper()
            if end_last in short_set or len(end_last) <= 2:
                combined = " ".join(end_tokens[:-1]).strip()

        if not re.search(r"[.!?]$", combined):
            combined += "."
        return combined

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
    # We DO NOT remove accents anymore for better readability in Portuguese.
    if not text:
        return ""
    
    # Converte espaços não-quebráveis (comuns em HTML) em espaços normais
    text = text.replace('\xa0', ' ')
    
    # Normaliza caracteres problemáticos que FFmpeg/Fontes costumam falhar em renderizar
    # Substitui reticências (single char) por três pontos normais
    text = text.replace('…', '...')
    # Substitui aspas curvas por retas
    text = text.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    # Substitui traços longos por hífens simples
    text = text.replace('—', '-').replace('–', '-')

    # Remove apenas caracteres de controle, mantém UTF-8 (acentos, pontuação básica)
    # Filtro rigoroso para evitar caixinhas com X
    sanitized = "".join(c for c in text if ord(c) >= 32 or c in "\n\r")
    
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

    return "\n".join(wrapped[:max_lines])


def _base_body_typography(line_count: int) -> tuple[int, int]:
    if line_count > 9:
        return 50, 60
    if line_count > 7:
        return 52, 62
    if line_count > 5:
        return 56, 68
    if line_count > 3:
        return 62, 75
    return 68, 85


def _layout_main_body_text(
    text: str,
    *,
    base_width: int = 34,
    max_lines: int = 11,
    min_scale: float = 0.84,
) -> tuple[list[str], int, int]:
    clean = " ".join((text or "").split())
    if not clean:
        return [], 68, 85

    scales = [1.0, 0.97, 0.94, 0.91, 0.88, 0.86, min_scale]
    baseline_lines = textwrap.wrap(clean, width=base_width, break_long_words=False, break_on_hyphens=False)
    base_font, base_spacing = _base_body_typography(len(baseline_lines))

    fallback_lines: list[str] = baseline_lines
    fallback_font = base_font
    fallback_spacing = base_spacing

    for scale in scales:
        width = max(30, int(round(base_width / scale)))
        lines = textwrap.wrap(clean, width=width, break_long_words=False, break_on_hyphens=False)
        font_size = max(43, int(round(base_font * scale)))
        line_spacing = max(52, int(round(base_spacing * scale)))
        fallback_lines = lines
        fallback_font = font_size
        fallback_spacing = line_spacing
        if len(lines) <= max_lines:
            return lines, font_size, line_spacing

    return fallback_lines[:max_lines], fallback_font, fallback_spacing


EDITORIAL_LAYOUT_PRESETS: list[dict[str, object]] = [
    {
        "name": "classic_center",
        "hook_width": 24,
        "hook_fontsize": 85,
        "hook_line_step": 104,
        "hook_base_y": 560,
        "hook_two_line_shift": 104,
        "hook_boxborderw": 18,
        "hook_x_mode": "center",
        "body_base_width": 34,
        "body_prefit_max_lines": 5,
        "body_prefit_min_scale": 0.72,
        "body_max_lines": 11,
        "body_min_scale": 0.84,
        "body_min_top_padding": 520,
        "body_x_mode": "center",
        "cta_fontsize": 53,
        "cta_y": "h*0.90",
        "cta_blink_period": 1.4,
        "cta_blink_on": 0.7,
    },
    {
        "name": "mag_strip",
        "hook_width": 22,
        "hook_fontsize": 89,
        "hook_line_step": 100,
        "hook_base_y": 500,
        "hook_two_line_shift": 90,
        "hook_boxborderw": 22,
        "hook_x_mode": "center",
        "body_base_width": 33,
        "body_prefit_max_lines": 5,
        "body_prefit_min_scale": 0.72,
        "body_max_lines": 10,
        "body_min_scale": 0.82,
        "body_min_top_padding": 560,
        "body_x_mode": "left",
        "body_left_x": 72,
        "cta_fontsize": 49,
        "cta_y": "h*0.885",
        "cta_blink_period": 1.6,
        "cta_blink_on": 0.8,
    },
    {
        "name": "wide_editorial",
        "hook_width": 26,
        "hook_fontsize": 79,
        "hook_line_step": 98,
        "hook_base_y": 540,
        "hook_two_line_shift": 86,
        "hook_boxborderw": 16,
        "hook_x_mode": "left",
        "hook_left_x": 60,
        "body_base_width": 36,
        "body_prefit_max_lines": 6,
        "body_prefit_min_scale": 0.72,
        "body_max_lines": 9,
        "body_min_scale": 0.83,
        "body_min_top_padding": 610,
        "body_x_mode": "left",
        "body_left_x": 64,
        "cta_fontsize": 50,
        "cta_y": "h*0.895",
        "cta_blink_period": 1.3,
        "cta_blink_on": 0.6,
    },
    {
        "name": "compact_bulletin",
        "hook_width": 23,
        "hook_fontsize": 83,
        "hook_line_step": 96,
        "hook_base_y": 610,
        "hook_two_line_shift": 92,
        "hook_boxborderw": 18,
        "hook_x_mode": "center",
        "body_base_width": 32,
        "body_prefit_max_lines": 5,
        "body_prefit_min_scale": 0.70,
        "body_max_lines": 11,
        "body_min_scale": 0.80,
        "body_min_top_padding": 500,
        "body_x_mode": "center",
        "cta_fontsize": 52,
        "cta_y": "h*0.91",
        "cta_blink_period": 1.2,
        "cta_blink_on": 0.55,
    },
]

EDITORIAL_COLORWAYS: list[dict[str, object]] = [
    {"hook_box_color": "0x111827", "hook_box_alpha": 0.95, "eq": "eq=brightness=-0.03:contrast=1.10:saturation=1.03"},
    {"hook_box_color": "0x7F1D1D", "hook_box_alpha": 0.94, "eq": "eq=brightness=-0.02:contrast=1.12:saturation=1.01"},
    {"hook_box_color": "0x1E293B", "hook_box_alpha": 0.95, "eq": "eq=brightness=-0.04:contrast=1.14:saturation=0.99"},
    {"hook_box_color": "0x1F2937", "hook_box_alpha": 0.93, "eq": "eq=brightness=-0.01:contrast=1.09:saturation=1.06"},
    {"hook_box_color": "0x422006", "hook_box_alpha": 0.94, "eq": "eq=brightness=-0.02:contrast=1.11:saturation=1.04"},
]


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _pick_editorial_style(seed_text: str) -> tuple[dict[str, object], dict[str, object]]:
    clean_seed = _clean_text(seed_text) or "editorial-style"
    digest = hashlib.sha1(clean_seed.encode("utf-8")).hexdigest()
    seed = int(digest, 16)
    layout = EDITORIAL_LAYOUT_PRESETS[seed % len(EDITORIAL_LAYOUT_PRESETS)]
    colorway = EDITORIAL_COLORWAYS[(seed // len(EDITORIAL_LAYOUT_PRESETS)) % len(EDITORIAL_COLORWAYS)]
    return layout, colorway


def _pick_logo_variant(seed_text: str) -> dict[str, object]:
    variants: list[dict[str, object]] = [
        {"name": "top_center_large", "x_mode": "center", "y": 28, "width": 372, "pulse": True, "pulse_amp": 18, "pulse_period": 68},
        {"name": "top_left_compact", "x_mode": "left", "x_margin": 42, "y": 32, "width": 290, "pulse": False},
        {"name": "top_right_compact", "x_mode": "right", "x_margin": 42, "y": 34, "width": 294, "pulse": False},
        {"name": "top_center_wide", "x_mode": "center", "y": 44, "width": 404, "pulse": True, "pulse_amp": 22, "pulse_period": 80},
        {"name": "top_left_featured", "x_mode": "left", "x_margin": 36, "y": 24, "width": 336, "pulse": True, "pulse_amp": 14, "pulse_period": 72},
        {"name": "top_right_featured", "x_mode": "right", "x_margin": 36, "y": 24, "width": 336, "pulse": True, "pulse_amp": 14, "pulse_period": 72},
    ]
    clean_seed = _clean_text(seed_text) or "logo-variant"
    digest = hashlib.sha1(clean_seed.encode("utf-8")).hexdigest()
    idx = int(digest, 16) % len(variants)
    return variants[idx]


def _logo_overlay_expr(variant: dict[str, object]) -> tuple[str, str, str, str]:
    x_mode = str(variant.get("x_mode", "center"))
    x_margin = _safe_int(variant.get("x_margin"), 36)
    y = str(_safe_int(variant.get("y"), 32))
    width = _safe_int(variant.get("width"), 340)
    pulse = bool(variant.get("pulse", False))
    pulse_amp = _safe_int(variant.get("pulse_amp"), 16)
    pulse_period = max(36, _safe_int(variant.get("pulse_period"), 72))

    if pulse:
        width_expr = f"{width}+{pulse_amp}*sin(2*PI*n/{pulse_period})"
    else:
        width_expr = str(width)

    if x_mode == "left":
        x_expr = str(x_margin)
    elif x_mode == "right":
        x_expr = f"W-w-{x_margin}"
    else:
        x_expr = "(W-w)/2"

    return width_expr, x_expr, y, str(variant.get("name", "logo_default"))


def _pick_image_motion_variant(seed_text: str, duration_s: float) -> tuple[list[str], str]:
    d = max(5.0, float(duration_s))
    d_str = f"{d:.2f}"
    variants: list[dict[str, str]] = [
        {
            "name": "zoom_in",
            "z": f"(1.000+0.034*t/{d_str})",
        },
        {
            "name": "zoom_out",
            "z": f"(1.034-0.034*t/{d_str})",
        },
    ]
    clean_seed = _clean_text(seed_text) or "image-motion"
    digest = hashlib.sha1(clean_seed.encode("utf-8")).hexdigest()
    idx = int(digest, 16) % len(variants)
    variant = variants[idx]
    z_expr = variant["z"]
    filters = [
        f"scale='1080*{z_expr}':'1920*{z_expr}':eval=frame:flags=lanczos",
        "crop=1080:1920:'floor((iw-1080)/2/2)*2':'floor((ih-1920)/2/2)*2'",
    ]
    return filters, variant["name"]


def _load_item_for_overlay_rewrite(out_video: Path, source: str) -> NewsItem | None:
    meta_path = out_video.parent / "news.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return NewsItem(
            source=meta.get("source") or source,
            feed_url=meta.get("feed_url") or "",
            title=meta.get("title") or "",
            link=meta.get("link") or "",
            published=meta.get("published") or "",
            image_url=meta.get("image_url") or "",
            description=meta.get("description") or "",
        )
    except Exception:
        return None


def _pick_pt_hook(headline: str) -> str:
    """Gera hooks em tom editorial-curioso para fallback local.

    Objetivo: soar menos genérico/repetido e mais específico do fato.
    """
    h = _clean_text(headline).lower()
    if any(k in h for k in ["morre", "morte", "luto", "velório", "velorio", "enterro", "falece"]):
        return random.choice(["UM DETALHE NO ADEUS CHOCOU A WEB", "O CLIMA DE LUTO TEVE REACAO INESPERADA"])
    if any(k in h for k in ["bbb", "big brother", "paredão", "paredao", "eliminação", "eliminacao", "prova do líder", "prova do lider", "anjo"]):
        return random.choice(["A JOGADA QUE MUDOU O CLIMA DA CASA", "NINGUEM ESPERAVA ESSE MOVIMENTO NO BBB"])
    if any(k in h for k in ["a fazenda", "reality", "peão", "peao"]):
        return random.choice(["O REALITY VIROU OUTRO DEPOIS DESSA CENA", "UMA FALA ACENDEU O CLIMA NO REALITY"])
    if any(k in h for k in ["filha", "filho", "bebê", "bebe", "gravidez", "grávida", "gravida", "nasceu"]):
        return random.choice(["A REVELACAO QUE PEGOU OS FAS DE SURPRESA", "NINGUEM VIU ESSE ANUNCIO CHEGAR"])
    if any(k in h for k in ["separ", "divórcio", "divorcio", "trai", "affair", "corno", "termina"]):
        return random.choice(["O SINAL QUE ANTECIPOU O FIM DO CASAL", "UM GESTO LEVANTOU SUSPEITA DE TERMINO"])
    if any(k in h for k in ["polêmica", "polemica", "briga", "treta", "confusão", "confusao", "desabaf"]):
        return random.choice(["A TRETA GANHOU OUTRO NIVEL NOS BASTIDORES", "UMA FALA DEIXOU A WEB DIVIDIDA"])
    if any(k in h for k in ["novela", "personagem", "ator", "atriz", "papel", "cena"]):
        return random.choice(["A CENA QUE VIROU ASSUNTO FORA DA NOVELA", "UMA MUDANCA DE ROTEIRO MEXEU COM A WEB"])
    if any(k in h for k in ["cirurgia", "hospital", "internado", "internada", "saúde", "saude", "doença", "doenca"]):
        return random.choice(["O BOLETIM TROUXE UM DETALHE DELICADO", "A ATUALIZACAO MEDICA GEROU ALERTA ENTRE FAS"])
    if any(k in h for k in ["namoro", "casal", "romance", "casamento", "noivar", "noivo", "noiva", "juntinhos", "flagrad", "beij"]):
        return random.choice(["UM FLAGRA REACENDEU OS RUMORES DO CASAL", "O MOMENTO QUE FEZ A WEB SHIPPAR DE NOVO"])
    if any(k in h for k in ["carnaval", "bloco", "fantasia", "desfile", "abadá", "abada"]):
        return random.choice(["UM DETALHE DA FANTASIA CHAMOU ATENCAO", "NO CARNAVAL ESSE MOMENTO NAO PASSOU BATIDO"])
    if any(k in h for k in ["pres", "cadeia", "processo", "policia", "policial", "detido", "detida"]):
        return random.choice(["O CASO GANHOU UM NOVO CAPITULO NA JUSTICA", "UMA VIRADA NO CASO SURPREENDEU A WEB"])
    if any(k in h for k in ["vingança", "vinganca", "estratégia", "estrategia", "articul", "plano"]):
        return random.choice(["A ESTRATEGIA QUE MUDOU O RUMO DO JOGO", "UM PLANO SILENCIOSO COM CONSEQUENCIA IMEDIATA"])
    return random.choice(["TEM UM DETALHE NESSA HISTORIA QUE INTRIGA", "ESSA CENA ACABOU VIRANDO ASSUNTO NA WEB"])


def _pick_en_hook(headline: str) -> str:
    """Generates editorial-curiosity hooks for local fallback."""
    h = _clean_text(headline).lower()
    if any(k in h for k in ["dies", "death", "dead", "passed away", "funeral"]):
        return random.choice(["ONE DETAIL IN THE FAREWELL SHOCKED FANS", "THE TRIBUTE MOMENT NOBODY EXPECTED"])
    if any(k in h for k in ["split", "divorce", "cheat", "scandal", "affair"]):
        return random.choice(["THE SIGN THAT HINTED THE BREAKUP EARLY", "ONE GESTURE REIGNITED CHEATING RUMORS"])
    if any(k in h for k in ["baby", "pregnan", "daughter", "son", "born"]):
        return random.choice(["THE ANNOUNCEMENT THAT CAUGHT FANS OFF GUARD", "NOBODY SAW THIS REVEAL COMING"])
    if any(k in h for k in ["arrest", "jail", "court", "lawsuit", "sued"]):
        return random.choice(["THE CASE JUST TOOK AN UNEXPECTED TURN", "A NEW COURT UPDATE CHANGED EVERYTHING"])
    if any(k in h for k in ["wedding", "engaged", "dating", "romance", "couple"]):
        return random.choice(["A SPOTTED MOMENT REIGNITED COUPLE RUMORS", "THE CLIP THAT MADE FANS SHIP AGAIN"])
    if any(k in h for k in ["fight", "feud", "clash", "drama", "beef"]):
        return random.choice(["ONE LINE PUSHED THIS FEUD TO A NEW LEVEL", "THE BACKSTAGE DETAIL SPLIT THE INTERNET"])
    return random.choice(["THERES ONE DETAIL HERE PEOPLE CANT IGNORE", "THIS MOMENT QUICKLY TOOK OVER THE INTERNET"])


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
    hook_text = _fit_hook_to_overlay(hook_text, max_chars=24, max_lines=2, min_words=6)
    hook = _wrap_for_overlay(hook_text, max_chars=24, max_lines=2, upper=True)

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
    summary_model = os.getenv("GOSSIP_SUMMARY_MODEL", cfg.model).strip()
    if is_openai_configured(cfg):
        try:
            api_key = os.getenv(cfg.api_key_env, "").strip()
            url = f"{cfg.base_url.rstrip('/')}/chat/completions"
            
            if is_pt:
                system_instr = (
                    "Voce e um roteirista viral de Shorts/Reels de fofoca brasileira. Seu estilo e inspirado nos posts que mais performam:\n\n"

                    "EXEMPLOS DE POSTS TOP (use como referencia de tom e estrutura):\n"
                    "Post 1: Hook='TRAVADINHA!' Body='BRUNA MARQUEZINE E SHAWN MENDES CURTEM CARNAVAL JUNTINHOS'\n"
                    "Post 2: Hook='JOGO SUJO' Body='BABU COBROU JOGO LIMPO E A TRETA EXPLODIU NA PROVA DO LIDER DO BBB 26, COM DISCUSSAO E ELIMINACOES.. VOCE APOIA...'\n"
                    "Post 3: Hook='ANA PAULA PLANEJA VINGANCA E COLOCA DUAS' Body='ELA ARTICULA PARA ELIMINAR SAMIRA E OUTROS ADVERSARIOS.. A WEB REAGE COM CHOQUE E CRITICAS AS ESTRATEGIAS AGRESSIVAS.'\n\n"

                    "FORMATO OBRIGATORIO — exatamente 5 linhas de TEXTO PURO:\n\n"

                    "Linha 1 = HOOK FACTUAL: Frase-curta editorial de curiosidade (preferencia 6 a 9 palavras; max 12). "
                    "Precisa soar especifica do caso e nao generica/repetida. "
                    "Evite ganchos de uma palavra tipo 'EITA'/'BOMBA' sem contexto.\n"
                    "Linha 2 = CONTEXTO (OBRIGATORIO iniciar com 'CONTEXTO:'): 1 frase objetiva com o fato principal e nomes.\n"
                    "Linha 3 = REACAO WEB (OBRIGATORIO iniciar com 'SEGUNDO FAS,'): reacao da web com suspense '..'. "
                    "Ex: 'SEGUNDO FAS, .. A CENA DIVIDIU OPINIOES'.\n"
                    "Linha 4 = DESDOBRAMENTO (OBRIGATORIO iniciar com 'A REPERCUSSAO COMECOU APOS'): consequencia ou impacto. "
                    "Se possivel termine com '...' (reticencias).\n"
                    "Linha 5 = CTA DE ENGAJAMENTO: frase imperativa curta para acao. "
                    "Ex: 'COMENTA O QUE ACHOU!', 'CURTE SE CONCORDA!', 'SALVA PRA VER DEPOIS!'\n\n"

                    "REGRAS DE OURO:\n"
                    "- Hook deve ter cara editorial: frase curta, especifica e com curiosidade.\n"
                    "- Evite hooks genericos/repetidos como 'EITA!' e 'BOMBA!'.\n"
                    "- Body (linhas 2-4) deve ser NARRATIVO, como se estivesse contando pra um amigo.\n"
                    "- Linhas 2, 3 e 4 juntas devem ter entre 20 e 32 palavras no total.\n"
                    "- Cada uma das linhas 2, 3 e 4 deve ter no maximo 11 palavras.\n"
                    "- Use '..' (dois pontos seguidos) para criar PAUSAS DRAMATICAS no meio do texto.\n"
                    "- Use '...' (reticencias) no FINAL para gerar curiosidade.\n"
                    "- Frases CURTAS e DIRETAS. Sem enrolacao.\n"
                    "- NUNCA comece o hook com 'VOCE', 'O QUE', 'VEJA', 'CONHECE'.\n"
                    "- Linguagem INFORMAL, como se falasse com amigo no WhatsApp.\n"
                    "- Linha 5 nao pode ser pergunta; deve ser CTA imperativo.\n"
                    "- ZERO hashtags.\n"
                    "- ZERO emojis.\n"
                    "- TODAS AS LINHAS EM CAPS LOCK.\n\n"

                    "Responda APENAS com as 5 linhas. Nada mais."
                )
                user_content = f"Noticia:\n{context}"
            else:
                system_instr = (
                    "You are a viral Shorts/Reels gossip scriptwriter. Your style is inspired by top-performing posts.\n\n"

                    "TOP POST EXAMPLES (use as tone/structure reference):\n"
                    "Post 1: Hook='CAUGHT!' Body='BRUNA MARQUEZINE AND SHAWN MENDES SPOTTED TOGETHER AT CARNIVAL'\n"
                    "Post 2: Hook='DIRTY GAME' Body='BABU DEMANDED FAIR PLAY AND THE FIGHT EXPLODED AT BBB 26 LEADER CHALLENGE, WITH ARGUMENTS AND ELIMINATIONS.. DO YOU SUPPORT...'\n"
                    "Post 3: Hook='REVENGE PLAN' Body='SHE PLOTS TO ELIMINATE SAMIRA AND OTHER RIVALS.. THE WEB REACTS WITH SHOCK AND CRITICISM.'\n\n"

                    "MANDATORY FORMAT — exactly 5 lines of plain text:\n\n"
                    "Line 1 = FACTUAL HOOK: Editorial curiosity line (prefer 6 to 9 words; max 12). "
                    "It must sound specific to the story, not generic/reused. "
                    "Avoid one-word hooks like 'WOW'/'BOMBSHELL' without context.\n"
                    "Line 2 = CONTEXT (MUST start with 'CONTEXT:'): one objective sentence with the main fact and names.\n"
                    "Line 3 = WEB REACTION (MUST start with 'ACCORDING TO FANS,'): include '..' suspense marker.\n"
                    "Line 4 = FOLLOW-UP (MUST start with 'THE BACKLASH STARTED AFTER'): consequence/impact and ideally end with '...'.\n"
                    "Line 5 = ENGAGEMENT CTA: short imperative call-to-action.\n"
                    "Ex: 'COMMENT YOUR TAKE!', 'LIKE IF YOU AGREE!', 'SAVE THIS POST!'\n\n"

                    "GOLDEN RULES:\n"
                    "- Hook should feel editorial: short, specific and curiosity-driven.\n"
                    "- Avoid repetitive generic hooks like 'WOW!'.\n"
                    "- Body (lines 2-4) must be NARRATIVE, like telling a friend.\n"
                    "- Lines 2, 3 and 4 combined must have 20 to 32 words total.\n"
                    "- Each of lines 2, 3 and 4 must have at most 11 words.\n"
                    "- Use '..' for DRAMATIC PAUSES in the middle of text.\n"
                    "- Use '...' at the END to create curiosity.\n"
                    "- Short, direct sentences. No fluff.\n"
                    "- NEVER start hook with 'YOU', 'WHAT', 'SEE', 'CHECK'.\n"
                    "- Informal language, like texting a friend.\n"
                    "- Line 5 must be imperative CTA, not a question.\n"
                    "- ALL CAPS, zero hashtags, zero emojis.\n\n"
                    "Respond ONLY with the 5 lines. Nothing before, nothing after."
                )
                user_content = f"News:\n{context}"

            payload = {
                "model": summary_model,
                "temperature": 0.7,
                "max_completion_tokens": 240,
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

    # Local fallback: preserve the fixed editorial signature in 5 lines.
    title = _clean_text(item.title) or "CASO VIROU ASSUNTO NAS REDES"
    desc = _clean_text(item.description)
    base = re.split(r"\s*[-:|]\s*", title, maxsplit=1)
    if len(base) == 2:
        factual = f"{base[0]}: {base[1]}"
    else:
        factual = title

    context_line = factual.rstrip(".")
    if len(context_line.split()) > 12:
        context_line = " ".join(context_line.split()[:12]).rstrip(" ,.;:-") + "..."

    reaction_hint = desc or title
    if len(reaction_hint.split()) > 10:
        reaction_hint = " ".join(reaction_hint.split()[:10]).rstrip(" ,.;:-") + "..."

    return "\n".join(
        [
            "DETALHE DO CASO ACENDEU DEBATE NAS REDES",
            f"CONTEXTO: {context_line}.",
            f"SEGUNDO FAS, .. {reaction_hint}",
            "A REPERCUSSAO COMECOU APOS O VIDEO VIRALIZAR...",
            "COMENTA O QUE ACHOU!",
        ]
    )


def _enforce_editorial_markers(body: str) -> str:
    """Guarantee editorial markers required for monetization-safe classification."""
    text = " ".join((body or "").split())
    if not text:
        text = "CONTEXTO: CASO VIROU ASSUNTO NAS REDES."
    if not re.search(r"\bCONTEXTO\s*:", text, flags=re.I):
        text = f"CONTEXTO: {text}"
    if not re.search(r"\bSEGUNDO\s+F[ÃA]S\b", text, flags=re.I):
        text = f"{text} SEGUNDO FAS, .. A WEB DIVIDIU OPINIOES."
    if not re.search(r"\bA\s+REPERCUSSAO\s+COMECOU\s+APOS\b", text, flags=re.I):
        text = f"{text} A REPERCUSSAO COMECOU APOS O TRECHO VIRALIZAR..."
    return " ".join(text.split())


def _strip_context_label(text: str) -> str:
    """Removes literal 'CONTEXTO:' label from overlay while keeping the sentence."""
    t = " ".join((text or "").split())
    t = re.sub(r"(^|\.\s+)\bCONTEXTO\s*:\s*", r"\1", t, flags=re.I)
    return " ".join(t.split())


def _send_video_to_telegram(video_path: Path, caption: str) -> bool:
    """Envia o vídeo gerado para o bot do Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID não configurados.")
        return False

    if not video_path.exists():
        print(f"⚠️ Vídeo não encontrado para envio: {video_path}")
        return False

    caption_clean = " ".join((caption or "").split())
    if len(caption_clean) > 1024:
        caption_clean = caption_clean[:1020].rsplit(" ", 1)[0] + "..."

    send_video_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    send_doc_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"

    last_error = "erro desconhecido"
    for attempt in range(1, 3):
        try:
            with open(video_path, "rb") as video:
                files = {"video": video}
                data = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": caption_clean,
                    "supports_streaming": True,
                }
                response = requests.post(send_video_url, files=files, data=data, timeout=120 + (attempt * 45))
            if response.status_code == 200:
                print("✅ Vídeo enviado com sucesso para o Telegram!")
                return True
            last_error = f"{response.status_code} - {response.text}"
            print(f"⚠️ Tentativa {attempt}/2 falhou no sendVideo: {last_error}")
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Tentativa {attempt}/2 falhou no sendVideo: {e}")

    # Fallback quando sendVideo falha por limite/formato: envia como documento.
    try:
        with open(video_path, "rb") as video:
            files = {"document": video}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption_clean}
            response = requests.post(send_doc_url, files=files, data=data, timeout=240)
        if response.status_code == 200:
            print("✅ Vídeo enviado como documento no Telegram (fallback).")
            return True
        print(f"❌ Falha no fallback sendDocument: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Falha no fallback sendDocument: {e}")

    print(f"❌ Erro final ao enviar para o Telegram: {last_error}")
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


def _rewrite_overlay_body_if_needed(text: str, *, item: NewsItem) -> str:
    """Rewrite body to fit overlay constraints when it would overflow or looks fragmentary."""
    t = " ".join((text or "").split())
    if not t:
        return t

    # rewrite triggers
    needs = False

    # common fragment patterns that look truncated on overlay
    if re.search(r"\bA WEB\b\s*\.?\s*$", t, flags=re.I):
        needs = True
    if re.search(r"\bA WEB\b\s*\.?\s*", t, flags=re.I) and len(t) < 180:
        # short texts containing 'A WEB' often end up as a dangling stub after wrapping
        needs = True
    if re.search(r"\b(ELE|ELA|ELES|ELAS)\s*$", t, flags=re.I):
        needs = True
    if re.search(r"\b(NAO|NÃO)\.$", t, flags=re.I):
        needs = True
    if t.endswith("..") or t.endswith(","):
        needs = True
    if len(t) > 200:
        needs = True

    if not needs:
        return t

    cfg = OpenAIConfig()
    if not is_openai_configured(cfg):
        # local fallback: remove dangling 'A WEB' and trailing stubs
        t2 = re.sub(r"\s*\bA WEB\b\s*\.?\s*$", "", t, flags=re.I).strip()
        t2 = re.sub(r"\s+\bNAO\.$", ".", t2, flags=re.I).strip()
        return t2 or t

    try:
        api_key = os.getenv(cfg.api_key_env, "").strip()
        url = f"{cfg.base_url.rstrip('/')}/chat/completions"

        context = _clean_text(f"{item.title}. {item.description}")
        context = context[:1600]

        payload = {
            "model": os.getenv("GOSSIP_OVERLAY_MODEL", os.getenv("GOSSIP_SUMMARY_MODEL", cfg.model)).strip() or cfg.model,
            "temperature": 0.6,
            "max_completion_tokens": 120,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Voce escreve TEXTO DE TELA (overlay) para shorts de fofoca BR. "
                        "Precisa ficar CURTO e com sentido completo. Sem emojis. Sem hashtags. "
                        "Nao termine com frase quebrada tipo 'A WEB.'."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Reescreva o corpo abaixo para caber em no max 5 linhas na tela.\n"
                        "Regras:\n"
                        "- 1 paragrafo unico, 120 a 160 caracteres (ideal).\n"
                        "- Comece com o fato principal (nomes).\n"
                        "- Inclua reacao da web ou consequencia, mas em frase completa.\n"
                        "- Pode usar '..' para pausa dramatica.\n"
                        "- Termine com ponto final ou reticencias '...'.\n\n"
                        f"Contexto da noticia: {context}\n\n"
                        f"Corpo atual: {t}"
                    ),
                },
            ],
        }

        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if r.status_code >= 400:
            return t
        data = r.json()
        out = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
        if not out:
            return t
        out = " ".join(str(out).split())
        # final guardrails
        out = re.sub(r"\s*\bA WEB\b\s*\.?\s*$", "", out, flags=re.I).strip()
        return out or t
    except Exception:
        return t


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
    duration_s: float = 5.0,
) -> None:
    ff = ensure_ffmpeg("tools")
    font = _ffmpeg_escape(_select_font())
    fade_out_start = max(0.0, duration_s - 1.2)
    cta_escaped = _ffmpeg_escape_text(_sanitize_cta_text(cta_text.upper()))
    (out_video.parent / "_overlay_text").mkdir(parents=True, exist_ok=True)

    SAFE_TOP = 220
    SAFE_BOTTOM = 1520

    main_path = summary_file or headline_file
    main_raw = main_path.read_text(encoding="utf-8") if main_path.exists() else ""
    main_clean = _sanitize_overlay_text(main_raw).replace("\xa0", " ")
    hook_raw = hook_file.read_text(encoding="utf-8") if hook_file and hook_file.exists() else ""
    hook_clean = _sanitize_overlay_text(hook_raw).replace("\xa0", " ")
    main_input = " ".join(main_clean.split())

    style_seed = f"{source}|{out_video.name}|{main_input}|{hook_clean}"
    layout, colorway = _pick_editorial_style(style_seed)
    motion_filters, _ = _pick_image_motion_variant(style_seed + "|motion", duration_s)
    logo_variant = _pick_logo_variant(style_seed + "|image")
    logo_scale_expr, logo_x_expr, logo_y_expr, _ = _logo_overlay_expr(logo_variant)
    hook_box_color = str(colorway.get("hook_box_color", "0x111827"))
    hook_box_alpha = _safe_float(colorway.get("hook_box_alpha"), 0.95)

    hook_width = _safe_int(layout.get("hook_width"), 24)
    hook_fontsize = _safe_int(layout.get("hook_fontsize"), 85)
    hook_line_step = _safe_int(layout.get("hook_line_step"), 104)
    hook_base_y_cfg = _safe_int(layout.get("hook_base_y"), 560)
    hook_two_line_shift = _safe_int(layout.get("hook_two_line_shift"), 104)
    hook_boxborderw = _safe_int(layout.get("hook_boxborderw"), 18)

    hook_lines = textwrap.wrap(hook_clean, width=hook_width, break_long_words=False, break_on_hyphens=False)[:2]
    hook_filters = []
    hook_base_y_raw = hook_base_y_cfg - (hook_two_line_shift if len(hook_lines) >= 2 else 0)
    hook_base_y = _clamp(hook_base_y_raw, SAFE_TOP, SAFE_BOTTOM)
    hook_x = "(w-tw)/2" if str(layout.get("hook_x_mode", "center")) != "left" else str(_safe_int(layout.get("hook_left_x"), 60))
    for i, line in enumerate(hook_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = _clamp(hook_base_y + (i * hook_line_step), SAFE_TOP, SAFE_BOTTOM)
        hook_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize={hook_fontsize}:fix_bounds=1:"
            f"borderw=3:bordercolor=black:"
            f"box=1:boxcolor={hook_box_color}@{hook_box_alpha:.2f}:boxborderw={hook_boxborderw}:"
            f"x={hook_x}:y={y_pos}"
        )

    prefit_width = _safe_int(layout.get("body_base_width"), 34)
    prefit_max_lines = _safe_int(layout.get("body_prefit_max_lines"), 5)
    prefit_min_scale = _safe_float(layout.get("body_prefit_min_scale"), 0.72)
    main_lines, font_size, line_spacing = _layout_main_body_text(
        main_input,
        base_width=prefit_width,
        max_lines=prefit_max_lines,
        min_scale=prefit_min_scale,
    )
    if (len(main_lines) > prefit_max_lines) or (main_lines and re.fullmatch(r"(A\s+)?WEB\.?", main_lines[-1].strip(), flags=re.I)):
        try:
            item_for_rewrite = _load_item_for_overlay_rewrite(out_video, source)
            if item_for_rewrite:
                main_input2 = _rewrite_overlay_body_if_needed(main_input, item=item_for_rewrite)
                main_lines, font_size, line_spacing = _layout_main_body_text(
                    main_input2,
                    base_width=prefit_width,
                    max_lines=prefit_max_lines,
                    min_scale=max(0.68, prefit_min_scale - 0.02),
                )
                main_input = main_input2
        except Exception:
            pass

    body_width = _safe_int(layout.get("body_base_width"), 34)
    body_max_lines = _safe_int(layout.get("body_max_lines"), 11)
    body_min_scale = _safe_float(layout.get("body_min_scale"), 0.84)
    main_lines, font_size, line_spacing = _layout_main_body_text(
        main_input,
        base_width=body_width,
        max_lines=body_max_lines,
        min_scale=body_min_scale,
    )
    main_filters = []
    main_x = "(w-tw)/2" if str(layout.get("body_x_mode", "center")) != "left" else str(_safe_int(layout.get("body_left_x"), 64))
    block_h = max(0, (len(main_lines) - 1) * line_spacing + font_size)
    top_padding = _safe_int(layout.get("body_min_top_padding"), 520)
    start_y = _clamp(SAFE_BOTTOM - block_h, SAFE_TOP + top_padding, SAFE_BOTTOM - font_size)

    for i, line in enumerate(main_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = start_y + (i * line_spacing)
        main_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize={font_size}:fix_bounds=1:"
            f"borderw=3:bordercolor=black:"
            f"x={main_x}:y={y_pos}"
        )

    cta_fontsize = _safe_int(layout.get("cta_fontsize"), 53)
    cta_y = str(layout.get("cta_y", "h*0.90"))
    cta_period = _safe_float(layout.get("cta_blink_period"), 1.4)
    cta_on = _safe_float(layout.get("cta_blink_on"), 0.7)
    cta_filter = (
        f"drawtext=text='{cta_escaped}':fontfile='{font}':fontcolor=white@0.88:"
        f"borderw=2:bordercolor=black:fontsize={cta_fontsize}:x=(w-text_w)/2:y={cta_y}:"
        f"enable='lt(mod(t\\,{cta_period:.2f})\\,{cta_on:.2f})'"
    )

    eq_filter = str(colorway.get("eq", "eq=brightness=-0.02:contrast=1.08:saturation=1.02"))
    vf_layers = [
        "scale=1080:-2",
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
        "setsar=1",
        "format=yuv420p",
        eq_filter,
        *motion_filters,
        *hook_filters,
        *main_filters,
        cta_filter,
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
            f"[0:v]{vf}[bg];[1:v]scale='{logo_scale_expr}':-1:eval=frame[logo];[bg][logo]overlay={logo_x_expr}:{logo_y_expr}[v]",
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
    cta_escaped = _ffmpeg_escape_text(_sanitize_cta_text(cta_text.upper()))

    SAFE_TOP = 220
    SAFE_BOTTOM = 1520

    main_path = summary_file or headline_file
    main_raw = main_path.read_text(encoding="utf-8") if main_path.exists() else ""
    main_clean = _sanitize_overlay_text(main_raw).replace("\xa0", " ")
    hook_raw = hook_file.read_text(encoding="utf-8") if hook_file and hook_file.exists() else ""
    hook_clean = _sanitize_overlay_text(hook_raw).replace("\xa0", " ")
    main_input = " ".join(main_clean.split())

    style_seed = f"{source}|{out_video.name}|{main_input}|{hook_clean}"
    layout, colorway = _pick_editorial_style(style_seed)
    logo_variant = _pick_logo_variant(style_seed + "|video")
    logo_scale_expr, logo_x_expr, logo_y_expr, _ = _logo_overlay_expr(logo_variant)
    hook_box_color = str(colorway.get("hook_box_color", "0x111827"))
    hook_box_alpha = _safe_float(colorway.get("hook_box_alpha"), 0.95)

    hook_width = _safe_int(layout.get("hook_width"), 24)
    hook_fontsize = _safe_int(layout.get("hook_fontsize"), 85)
    hook_line_step = _safe_int(layout.get("hook_line_step"), 104)
    hook_base_y_cfg = _safe_int(layout.get("hook_base_y"), 560)
    hook_two_line_shift = _safe_int(layout.get("hook_two_line_shift"), 104)
    hook_boxborderw = _safe_int(layout.get("hook_boxborderw"), 18)

    hook_lines = textwrap.wrap(hook_clean, width=hook_width, break_long_words=False, break_on_hyphens=False)[:2]
    hook_filters = []
    hook_base_y_raw = hook_base_y_cfg - (hook_two_line_shift if len(hook_lines) >= 2 else 0)
    hook_base_y = _clamp(hook_base_y_raw, SAFE_TOP, SAFE_BOTTOM)
    hook_x = "(w-tw)/2" if str(layout.get("hook_x_mode", "center")) != "left" else str(_safe_int(layout.get("hook_left_x"), 60))
    for i, line in enumerate(hook_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = _clamp(hook_base_y + (i * hook_line_step), SAFE_TOP, SAFE_BOTTOM)
        hook_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize={hook_fontsize}:fix_bounds=1:"
            f"borderw=3:bordercolor=black:"
            f"box=1:boxcolor={hook_box_color}@{hook_box_alpha:.2f}:boxborderw={hook_boxborderw}:"
            f"x={hook_x}:y={y_pos}"
        )

    prefit_width = _safe_int(layout.get("body_base_width"), 34)
    prefit_max_lines = _safe_int(layout.get("body_prefit_max_lines"), 5)
    prefit_min_scale = _safe_float(layout.get("body_prefit_min_scale"), 0.72)
    main_lines, font_size, line_spacing = _layout_main_body_text(
        main_input,
        base_width=prefit_width,
        max_lines=prefit_max_lines,
        min_scale=prefit_min_scale,
    )
    if (len(main_lines) > prefit_max_lines) or (main_lines and re.fullmatch(r"(A\s+)?WEB\.?", main_lines[-1].strip(), flags=re.I)):
        try:
            item_for_rewrite = _load_item_for_overlay_rewrite(out_video, source)
            if item_for_rewrite:
                main_input2 = _rewrite_overlay_body_if_needed(main_input, item=item_for_rewrite)
                main_lines, font_size, line_spacing = _layout_main_body_text(
                    main_input2,
                    base_width=prefit_width,
                    max_lines=prefit_max_lines,
                    min_scale=max(0.68, prefit_min_scale - 0.02),
                )
                main_input = main_input2
        except Exception:
            pass

    body_width = _safe_int(layout.get("body_base_width"), 34)
    body_max_lines = _safe_int(layout.get("body_max_lines"), 11)
    body_min_scale = _safe_float(layout.get("body_min_scale"), 0.84)
    main_lines, font_size, line_spacing = _layout_main_body_text(
        main_input,
        base_width=body_width,
        max_lines=body_max_lines,
        min_scale=body_min_scale,
    )
    main_filters = []
    main_x = "(w-tw)/2" if str(layout.get("body_x_mode", "center")) != "left" else str(_safe_int(layout.get("body_left_x"), 64))

    block_h = max(0, (len(main_lines) - 1) * line_spacing + font_size)
    top_padding = _safe_int(layout.get("body_min_top_padding"), 520)
    start_y = _clamp(SAFE_BOTTOM - block_h, SAFE_TOP + top_padding, SAFE_BOTTOM - font_size)

    for i, line in enumerate(main_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = start_y + (i * line_spacing)
        main_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize={font_size}:fix_bounds=1:"
            f"borderw=3:bordercolor=black:"
            f"x={main_x}:y={y_pos}"
        )

    cta_fontsize = _safe_int(layout.get("cta_fontsize"), 53)
    cta_y = str(layout.get("cta_y", "h*0.90"))
    cta_period = _safe_float(layout.get("cta_blink_period"), 1.4)
    cta_on = _safe_float(layout.get("cta_blink_on"), 0.7)
    cta_filter = (
        f"drawtext=text='{cta_escaped}':fontfile='{font}':fontcolor=white@0.88:"
        f"borderw=2:bordercolor=black:fontsize={cta_fontsize}:x=(w-text_w)/2:y={cta_y}:"
        f"enable='lt(mod(t\\,{cta_period:.2f})\\,{cta_on:.2f})'"
    )

    eq_filter = str(colorway.get("eq", "eq=brightness=-0.02:contrast=1.08:saturation=1.02"))
    scale_filters = [
        "scale=1080:-2",
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
        "setsar=1",
        "format=yuv420p",
        eq_filter,
    ]
    text_filters = [
        *hook_filters,
        *main_filters,
        cta_filter,
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
            # Escala logo com variante editorial por post
            f"[1:v]scale='{logo_scale_expr}':-1:eval=frame[logo];"
            # Overlay do logo com posicao variavel
            f"[bg][logo]overlay={logo_x_expr}:{logo_y_expr}[v]",
            "-map",
            "[v]",
            "-map",
            "0:a?",
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
            "0:a?",
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


def _normalize_pt_hook(hook: str, headline: str) -> str:
    """Fixes odd/rare PT-BR hooks produced by the model.

    - Avoids uncommon verb-only hooks like 'CONFISSOU!'
    - Avoids weird constructions like 'EITA CONFISSOU!'
    """
    if not hook:
        return hook

    h = _clean_text(hook).upper().strip()
    h = re.sub(r"\s+", " ", h)

    hh = _clean_text(headline).lower()

    def _fallback() -> str:
        if any(k in hh for k in ["bbb", "pared", "big brother", "lider", "anjo"]):
            return random.choice(["ABRIU O JOGO!", "EITA!", "JOGO SUJO", "PEGOU FOGO!"])
        if any(k in hh for k in ["confiss", "revel", "segredo", "abriu o jogo"]):
            return random.choice(["ABRIU O JOGO!", "BOMBA!", "EITA!"])
        return random.choice(["EITA!", "BOMBA!", "PESOU!"])

    # Case 1: verb-only hook (sounds unnatural in BR gossip overlay)
    verb_only_bad = {"CONFISSOU!", "REVELOU!", "ASSUMIU!", "DESABAFOU!"}
    if h in verb_only_bad:
        return _fallback()

    # Case 2: 'EITA X!'
    m = re.match(r"^(EITA)\s+([A-ZÀ-Ü]+)\!$", h)
    if m:
        word = m.group(2)
        banned = {"CONFISSOU", "REVELOU", "ASSUMIU", "DESABAFOU"}
        if word in banned:
            return _fallback()

    # Generic cleanup
    h = h.rstrip(".")
    if h.endswith("..."):
        h = h[:-3].strip() + "!"
    return h


def _specialize_pt_hook(hook: str, headline: str) -> str:
    """Reduce generic PT hooks by replacing broad hooks with context-aware alternatives."""
    h = _clean_text(hook).upper().strip()
    title = _clean_text(headline).lower()
    generic = {"EITA!", "BOMBA!", "CHOCANTE!", "SURREAL!", "PESOU!"}

    if h and h not in generic:
        return h

    if any(k in title for k in ["confiss", "revel", "abriu o jogo", "segredo", "assum"]):
        return "ABRIU O JOGO!"
    if any(k in title for k in ["bbb", "paredão", "paredao", "elimina", "votação", "votacao"]):
        return "NO ALVO!"
    if any(k in title for k in ["briga", "treta", "discuss", "barraco", "bate-boca"]):
        return "TRETA NO AR!"
    if any(k in title for k in ["beij", "romance", "casal", "namoro"]):
        return "CLIMA ESQUENTOU!"
    if any(k in title for k in ["pris", "polic", "process", "detid"]):
        return "CASO PESADO!"

    options = ["ABRIU O JOGO!", "PEGOU FOGO!", "TRETA NO AR!", "CLIMA TENSO!"]
    idx = int(hashlib.md5((headline or "").encode("utf-8")).hexdigest(), 16) % len(options)
    return options[idx]


def _upgrade_hook_if_too_short(hook: str, headline: str, source: str) -> str:
    """Promote short/generic hooks into context-aware editorial hooks."""
    cleaned = _clean_text(hook).upper().strip()
    words = [w for w in cleaned.split() if w]
    is_pt = _is_portuguese_context(source, headline)

    generic_pt = {"EITA!", "BOMBA!", "CHOCANTE!", "SURREAL!", "PESOU!", "TRETA!"}
    generic_en = {"WOW!", "WILD!", "SHOCKING!", "BOMBSHELL!", "NO WAY!", "DRAMA!"}

    if is_pt:
        if len(words) < 6 or cleaned in generic_pt:
            return _pick_pt_hook(headline)
        return cleaned

    if len(words) < 6 or cleaned in generic_en:
        return _pick_en_hook(headline)
    return cleaned


def create_post_for_item(item: NewsItem, args: argparse.Namespace) -> bool:
    """Função centralizada para criar um post a partir de um NewsItem."""
    root = Path(__file__).resolve().parents[1]
    post_dir = root / "gossip_post"
    post_dir.mkdir(parents=True, exist_ok=True)
    hook_history_path = post_dir / HOOK_HISTORY_FILE

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
        # Linha 5 agora é CTA emocional (não mais pergunta polarizada)
        ai_cta = ""
        if len(content_lines) >= 5:
            hook = content_lines[0]
            # Combine Fact + Reaction + Impact into body
            body = f"{content_lines[1]} {content_lines[2]} {content_lines[3]}"
            ai_cta = content_lines[4]  # CTA sugerido pela IA
            headline_text = body
        elif len(content_lines) == 4:
            hook = content_lines[0]
            body = f"{content_lines[1]} {content_lines[2]}"
            ai_cta = content_lines[3]
            headline_text = body
        elif len(content_lines) == 3:
            hook = content_lines[0]
            body = content_lines[1]
            ai_cta = content_lines[2]
            headline_text = body
        elif len(content_lines) == 2:
            hook = content_lines[0]
            headline_text = content_lines[1]
        elif len(content_lines) == 1:
            single_line = content_lines[0]
            if len(single_line.split()) <= 5 and re.search(r"[!?]$", single_line):
                hook = single_line
                _, headline_text = _build_text_layers(item.title, item.source)
            else:
                hook, _ = _build_text_layers(item.title, item.source)
                headline_text = single_line
        else:
            hook, headline_text = _build_text_layers(item.title, item.source)

        # ── Limpeza leve (sem truncamento agressivo) ──
        # Remove hashtags residuais e caracteres problemáticos, preserva pontuação
        hook_clean = re.sub(r'#\w+', '', hook).strip()
        hook_clean = re.sub(r"[^\w\s\u00C0-\u00FF?!]", '', hook_clean)
        hook_clean = re.sub(r'\s+', ' ', hook_clean).strip()
        if _is_probably_bad_hook(hook_clean):
            hook_clean = _pick_pt_hook(item.title) if _is_portuguese_context(item.source, item.title) else _pick_en_hook(item.title)
        # Ajuste PT-BR: evita hooks estranhos (ex.: 'EITA CONFISSOU!')
        if _is_portuguese_context(item.source, item.title):
            hook_clean = _normalize_pt_hook(hook_clean, item.title)
            hook_clean = _specialize_pt_hook(hook_clean, item.title)
        hook_clean = _upgrade_hook_if_too_short(hook_clean, item.title, item.source)
        # Encaixa no overlay sem cortar palavras finais.
        hook_clean = _fit_hook_to_overlay(hook_clean, max_chars=24, max_lines=2, min_words=6)
        # Evita repetir estruturas de hook em publicações consecutivas.
        recent_hooks = _load_recent_hook_history(hook_history_path, window=HOOK_HISTORY_WINDOW)
        hook_clean = _diversify_hook_if_reused(
            hook_clean,
            headline=item.title,
            source=item.source,
            recent_hooks=recent_hooks,
        )
        hook_clean = _trim_trailing_connectors(hook_clean)

        headline_text = _enforce_editorial_markers(headline_text)
        headline_text = _strip_context_label(headline_text)
        headline_text_clean = re.sub(r'#\w+', '', headline_text).strip()
        # Preserva '..' (suspense) e '...' (curiosidade) - padrão dos posts top
        headline_text_clean = re.sub(r'[^\w\s\u00C0-\u00FF.,!?]', '', headline_text_clean)
        headline_text_clean = re.sub(r'\s+', ' ', headline_text_clean).strip()
        headline_text_clean = _fix_orphan_pronoun_tail(headline_text_clean)
        # Normaliza o marcador dramático: evita ' . .. ' e garante apenas '..' com espaços ao redor
        headline_text_clean = re.sub(r"\s*\.{1,2}\s*\.\.\s*", " .. ", headline_text_clean)
        headline_text_clean = re.sub(r"\s*\.\.\s*", " .. ", headline_text_clean)
        headline_text_clean = re.sub(r"\s{2,}", " ", headline_text_clean).strip()
        headline_text_clean = _polish_body_punctuation(headline_text_clean)
        # Evita finais truncados tipo 'A WEB.'
        headline_text_clean = _fix_web_fragment(headline_text_clean)
        # Se o corpo aparentar fragmento (ex.: termina com 'TEM QUE SABER O MEU...'), tenta completar
        headline_text_clean = _ensure_headline_completeness(headline_text_clean, item)
        # Passo final anti-fragmento para overlays curtos.
        headline_text_clean = _rewrite_overlay_body_if_needed(headline_text_clean, item=item)
        if _is_bad_overlay_body(headline_text_clean):
            headline_text_clean = _clean_text(f"{item.title}. A WEB REAGIU E O TEMA VIRALIZOU NAS REDES...")
            headline_text_clean = _rewrite_overlay_body_if_needed(headline_text_clean, item=item)
        # Evita corpo gigante e NÃO corta no meio da última frase
        # (limite pensado para caber em ~7-8 linhas na overlay)
        headline_text_clean = _truncate_at_sentence_boundary(headline_text_clean, max_chars=320)

        # Garante pontuação final para sensação de completude
        if headline_text_clean and not re.search(r"[.!?]$", headline_text_clean):
            headline_text_clean += "?" if "?" in headline_text_clean else "."

        # Força caixa alta
        headline_text_clean = headline_text_clean.upper()
        
        # Hook: 24 chars por linha, máximo 2 linhas (mais natural para frase editorial curta)
        hook_wrapped = _wrap_for_overlay(hook_clean, max_chars=24, max_lines=2, upper=True)
        
        hook_file = post_dir / "hook.txt"
        hook_file.write_text(_sanitize_overlay_text(hook_wrapped) + "\n", encoding="utf-8")
        _save_hook_to_history(hook_history_path, hook_clean, title=item.title, source=item.source)

        summary_file = post_dir / "summary.txt"
        summary_file.write_text(_sanitize_overlay_text(headline_text_clean) + "\n", encoding="utf-8")

        # Display headline: concise summary of the full news message.
        headline = _build_display_headline(headline_text_clean)
        headline_file = post_dir / "headline.txt"
        headline_file.write_text(_sanitize_overlay_text(headline) + "\n", encoding="utf-8")
        image_duration_s = round(random.uniform(5.0, 8.0), 2)

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
            "video_duration_s": image_duration_s,
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

        # ── CTA: Prefere CTA da IA (linha 5), fallback para CTA temático ──
        # A IA agora gera CTAs emocionais como "COMENTA O QUE ACHOU!", "CURTE SE GOSTA DE EMOCAO NO BBB"
        if _is_valid_ai_cta(ai_cta):
            # Usa o CTA gerado pela IA (já otimizado para o tema)
            cta_text = _sanitize_cta_text(ai_cta.upper())
        else:
            # Fallback: CTA temático baseado no conteúdo da notícia
            cta_text = _sanitize_cta_text(_get_random_cta(item.title, headline=headline_text_clean))
        
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
            summary_file=summary_file,
            cta_text=cta_text,
            logo_path=logo_path,
            duration_s=image_duration_s,
        )

        # Adiciona um pequeno delay para garantir que o arquivo de vídeo seja liberado pelo SO
        import time
        time.sleep(1)

        # Telegram Notification with hashtags in caption
        # Clean up hook and headline for better formatting (já estão limpos, sem hashtags)
        hook_telegram = " ".join(hook_clean.split())  # Remove extra spaces/newlines
        headline_telegram = " ".join(headline_text_clean.split())  # Single line
        
        telegram_title = " ".join(_clean_text(item.title).split()) or headline_telegram
        telegram_description = f"{hook_telegram} {headline_telegram}".strip()
        if len(telegram_description) > 520:
            telegram_description = telegram_description[:520].rsplit(" ", 1)[0] + "..."
        cta_for_caption = " ".join(_clean_text(cta_text).split()) if cta_text else "COMENTA O QUE ACHOU!"
        telegram_caption = (
            "🔥 BABADO RAPIDO\n\n"
            f"🧨 Hook: {hook_telegram}\n"
            f"📰 Titulo: {telegram_title}\n"
            f"📝 Resumo: {telegram_description}\n"
            f"💬 CTA: {cta_for_caption}\n\n"
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
    p = argparse.ArgumentParser(description="Create gossip shorts from RSS feeds.")
    p.add_argument("--profile", choices=("br", "intl"), default="br")
    p.add_argument("--url", default="", help="Direct link to a news article.")
    p.add_argument(
        "--video-url",
        default="",
        help="Backward-compatible alias for --url used by Telegram video queue.",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Legacy Telegram argument kept for compatibility (currently unused).",
    )
    p.add_argument("--logo", default="", help="Optional logo path (png/webp/jpg).")
    p.add_argument("--count", type=int, default=1, help="Number of posts to generate.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    input_url = args.url or args.video_url

    if input_url:
        print(f"🔗 Processando URL direta: {input_url}")
        # Tenta identificar a fonte pelo domínio
        source = "custom"
        for name, _ in FEED_PROFILES["br"] + FEED_PROFILES["intl"]:
            if name in input_url:
                source = name
                break
        item = _fetch_news_from_url(input_url, source)
        if not item:
            print("❌ Não foi possível obter conteúdo da URL informada.")
            return 1
        if not create_post_for_item(item, args):
            return 1
        return 0
    else:
        feeds = FEED_PROFILES[args.profile]
        processed_titles = []
        count = getattr(args, "count", 1)
        
        for i in range(count):
            try:
                item = _fetch_first_news(feeds, skip_titles=processed_titles)
                if item:
                    print(f"🚀 Processando item {i+1}/{count}: {item.title}")
                    if create_post_for_item(item, args):
                        processed_titles.append(item.title)
                    else:
                        print(f"⚠️ Falha ao criar post {i+1}")
                else:
                    print("🏁 Não há mais notícias novas nos feeds.")
                    break
            except Exception as e:
                print(f"❌ Erro no loop de geração: {e}")
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
