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


def _trim_sentence_words(text: str, *, max_words: int = 16) -> str:
    words = [w for w in " ".join((text or "").split()).split(" ") if w]
    if not words:
        return ""
    if len(words) > max_words:
        words = words[:max_words]
    out = " ".join(words).rstrip(" ,;:-")
    if out and not re.search(r"[.!?]$", out):
        out += "."
    return out


def _split_sentences(text: str) -> list[str]:
    clean = _clean_text(text)
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?])\s+", clean)
    out: list[str] = []
    for part in parts:
        sentence = " ".join(part.strip().split())
        sentence = sentence.strip(" .")
        if sentence:
            out.append(sentence)
    return out


def _build_editorial_description(description_text: str, item: NewsItem) -> tuple[str, str]:
    """Ensure the off-video description follows V4: two short interpretive lines."""
    clean = _clean_text(description_text)
    clean = re.sub(r"https?://\S+", "", clean).strip()
    clean = _truncate_at_sentence_boundary(clean, max_chars=220)
    parts = _split_sentences(clean)

    if len(parts) >= 2:
        line1_raw = parts[0]
        line2_raw = parts[1]
    else:
        title_base = _clean_text(item.title)
        title_base = re.split(r"\s*[-:|]\s*", title_base, maxsplit=1)[0]
        title_base = " ".join(title_base.split()[:12]).strip()
        if not title_base:
            title_base = "A historia"
        line1_raw = f"{title_base} virou assunto"
        line2_raw = "A web reagiu e as opinioes ficaram divididas"

    line1 = _trim_sentence_words(line1_raw, max_words=15)
    line2 = _trim_sentence_words(line2_raw, max_words=15)

    if not line1:
        line1 = "O caso chamou atencao nas redes."
    if not line2:
        line2 = "A web reagiu e as opinioes ficaram divididas."

    return line1, line2


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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


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


def _clean_description_boilerplate(text: str, *, title: str = "") -> str:
    """Remove RSS boilerplate fragments and duplicated lead chunks."""
    t = _clean_text(text)
    if not t:
        return t

    # Common CMS feed suffixes.
    t = re.sub(r"\bO post\b.*?\bapareceu primeiro em\b.*$", "", t, flags=re.I)
    t = re.sub(r"\bThe post\b.*?\bfirst appeared on\b.*$", "", t, flags=re.I)
    t = re.sub(r"\bLeia mais\b.*$", "", t, flags=re.I)
    t = re.sub(r"\bContinue reading\b.*$", "", t, flags=re.I)

    # Deduplicate repeated leading token blocks (e.g. "Piorou? Piorou? Defesa ...").
    tokens = [tk for tk in t.split() if tk]
    for n in range(3, 8):
        if len(tokens) >= 2 * n and [w.lower() for w in tokens[:n]] == [w.lower() for w in tokens[n:2 * n]]:
            tokens = tokens[:n] + tokens[2 * n :]
            break
    t = " ".join(tokens).strip()

    if title:
        title_clean = _clean_text(title)
        if title_clean:
            pattern = re.escape(title_clean)
            t = re.sub(rf"^(?:{pattern}\s+)+", f"{title_clean} ", t, flags=re.I).strip()

    t = re.sub(r"\s{2,}", " ", t).strip(" .")
    return t


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


def _smart_truncate_hook(hook_raw: str, max_words: int = 8) -> str:
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


def _fit_hook_to_overlay(hook: str, *, max_chars: int = 24, max_lines: int = 3, min_words: int = 5) -> str:
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


def _is_probably_bad_hook(text: str) -> bool:
    t = _clean_text(text).upper()
    if not t:
        return True
    if t.startswith(("CONTEXTO", "CONTEXT", "SEGUNDO FAS", "ACCORDING TO FANS", "A REPERCUSSAO", "THE BACKLASH")):
        return True
    if re.search(r"\b(E|OU)\s+\1\b", t):
        return True
    if re.search(r"\b(LINHA|LINE)\s*\d+\b", t):
        return True
    if _looks_incomplete_pt_line(t):
        return True
    words = [w for w in t.split() if w]
    return len(words) < 5


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


GENERIC_HOOK_PATTERNS_PT = [
    "TEM UM DETALHE",
    "NESSA HISTORIA",
    "ESSA CENA",
    "QUE BABADO",
    "DEU O QUE FALAR",
]


def _is_overgeneric_hook(hook: str) -> bool:
    normalized = _normalize_hook_text(hook)
    if not normalized:
        return True
    return any(marker in normalized for marker in GENERIC_HOOK_PATTERNS_PT)


def _generate_contextual_hook_with_ai(item: NewsItem, recent_hooks: list[str], fallback: str = "") -> str | None:
    """Generate a context-aware hook (5-10 words) using OpenAI when available."""
    cfg = OpenAIConfig()
    if not is_openai_configured(cfg):
        return None

    api_key = os.getenv(cfg.api_key_env, "").strip()
    if not api_key:
        return None

    is_pt = _is_portuguese_context(item.source, item.title)
    context = _clean_text(f"{item.title}. {item.description}")[:1200]
    recent = ", ".join(recent_hooks[-8:]) if recent_hooks else "nenhum"
    fallback_clean = _clean_text(fallback)

    if is_pt:
        system_content = (
            "Voce escreve HOOK editorial para short de fofoca BR.\n"
            "Retorne APENAS 1 linha, sem label, com 5 a 10 palavras.\n"
            "Regras obrigatorias:\n"
            "- Pode ser pergunta OU afirmacao de impacto.\n"
            "- Trazer elemento especifico da noticia (nome, caso ou consequencia).\n"
            "- Nao usar ganchos genericos como 'TEM UM DETALHE NESSA HISTORIA'.\n"
            "- Precisa ser frase completa, sem final truncado ou conectivo solto.\n"
            "- Nao repetir hooks recentes.\n"
            "- Sem hashtags e sem emojis."
        )
        user_content = (
            f"Noticia: {context}\n"
            f"Hooks recentes proibidos: {recent}\n"
            f"Hook atual (fraco): {fallback_clean or 'nenhum'}\n"
            "Gere um hook melhor agora."
        )
    else:
        system_content = (
            "You write an editorial HOOK for gossip shorts.\n"
            "Return ONLY 1 line, 5 to 10 words.\n"
            "Can be a question OR an impact statement, specific to the context.\n"
            "No generic hooks, no hashtags, no emojis, and no repetition."
        )
        user_content = (
            f"News: {context}\n"
            f"Recent blocked hooks: {recent}\n"
            f"Weak current hook: {fallback_clean or 'none'}"
        )

    payload = {
        "model": os.getenv("GOSSIP_SUMMARY_MODEL", cfg.model).strip() or cfg.model,
        "temperature": 0.85,
        "max_completion_tokens": 72,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
    }

    try:
        r = requests.post(
            f"{cfg.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
        if not content:
            return None

        line = ""
        for raw in str(content).splitlines():
            candidate = raw.strip()
            if not candidate:
                continue
            if candidate.startswith("#"):
                continue
            line = re.sub(r"^(hook|gancho)\s*[:\-–—=]\s*", "", candidate, flags=re.I).strip()
            if line:
                break
        if not line:
            return None

        line = re.sub(r"[^\w\s\u00C0-\u00FF?!]", "", line)
        line = re.sub(r"\s+", " ", line).strip().upper()
        line = _smart_truncate_hook(line, max_words=8)
        line = _fit_hook_to_overlay(line, max_chars=24, max_lines=3, min_words=5)

        if not line:
            return None
        word_count = len([w for w in line.replace("?", "").replace("!", "").split() if w])
        if word_count < 5 or word_count > 10:
            return None
        if _looks_incomplete_pt_line(line):
            return None
        if _is_overgeneric_hook(line):
            return None
        if _normalize_hook_text(line) in set(recent_hooks):
            return None
        return line
    except Exception:
        return None


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

    if not isinstance(payload, dict):
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


def _pick_first_existing_font(paths: list[Path | str], fallback: str) -> str:
    for p in paths:
        candidate = Path(p) if not isinstance(p, Path) else p
        if candidate.exists():
            return str(candidate)
    return fallback


def _select_hook_font() -> str:
    return _pick_first_existing_font(
        [
            ROOT_DIR / "assets" / "fonts" / "BebasNeue-Bold.ttf",
            ROOT_DIR / "assets" / "fonts" / "BebasNeue-Regular.ttf",
            "/System/Library/Fonts/Supplemental/Impact.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ],
        "/System/Library/Fonts/Helvetica.ttc",
    )


def _select_body_font() -> str:
    return _pick_first_existing_font(
        [
            ROOT_DIR / "assets" / "fonts" / "Poppins-Black.ttf",
            ROOT_DIR / "assets" / "fonts" / "Poppins-ExtraBold.ttf",
            ROOT_DIR / "assets" / "fonts" / "Poppins-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Poppins-Black.ttf",
            "/System/Library/Fonts/Supplemental/Poppins-ExtraBold.ttf",
            "/System/Library/Fonts/Supplemental/Poppins-Bold.ttf",
            "/Library/Fonts/Poppins-Black.ttf",
            "/Library/Fonts/Poppins-ExtraBold.ttf",
            "/Library/Fonts/Poppins-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Avenir Next Condensed Heavy.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ],
        "/System/Library/Fonts/Helvetica.ttc",
    )


def _select_font() -> str:
    # Backward-compatible alias used in older code paths.
    return _select_hook_font()


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


def _is_portuguese_context(source: str, headline: str) -> bool:
    # Strict check for BR portals
    if source in {"contigo", "ofuxico", "terra_gente", "ig_gente"}:
        return True
    h = _clean_text(headline).lower()
    pt_markers = [" não ", " com ", " para ", " dos ", " das ", "você", "fofoca", "famosos", " é ", " o ", " a "]
    return any(m in h for m in pt_markers)


def _headline_for_overlay(headline: str, max_chars: int = 24, max_lines: int = 5) -> str:
    # Backward-compat helper for scripts that still call this.
    return _wrap_for_overlay(headline, max_chars=max_chars, max_lines=max_lines, upper=True)


def _build_display_headline(headline: str) -> str:
    clean = _clean_text(headline)
    words = [w for w in clean.split() if w]
    if not words:
        return "Treta nova"
    return " ".join(words[:14])


def _extract_headline_subject(title: str) -> str:
    words = [w for w in re.sub(r"[^\w\s\u00C0-\u00FF]", " ", _clean_text(title)).split() if w]
    if not words:
        return "Web"

    ignored = {
        "tres", "três", "gracas", "graças", "atitude", "novela", "bbb", "big", "brother",
        "famosos", "caso", "video", "vídeo", "portal", "web", "reality",
    }
    for w in words:
        norm = w.lower()
        if norm in ignored:
            continue
        if len(norm) <= 2:
            continue
        if w[:1].isupper():
            return w
    return words[0]


def _enforce_editorial_headline(headline: str, source_title: str) -> str:
    base = _build_display_headline(headline)
    words = [w for w in base.split() if w]
    bad_starts = {"atitude", "novela", "tres", "três", "caso"}

    if len(words) >= 7 and words[0].lower() not in bad_starts:
        return base

    subject = _extract_headline_subject(source_title)
    theme = _detect_news_theme(source_title)
    action_by_theme = {
        "bbb": "muda o clima do reality e acende debate",
        "treta": "entra em confronto e estoura nova crise",
        "namoro": "vira assunto apos flagra e reacao publica",
        "separacao": "adota postura que amplia rumor de termino",
        "morte": "gera emocao e discussao nas redes",
        "carnaval": "vira pauta apos detalhe que dividiu opinioes",
        "gravidez": "surpreende e provoca reacao imediata da web",
        "policia": "ganha novo capitulo e aumenta pressao publica",
        "generic": "vira centro de uma reviravolta com repercussao",
    }
    action = action_by_theme.get(theme, action_by_theme["generic"])
    return " ".join(f"{subject} {action}".split()[:14])


def _count_words(text: str) -> int:
    return len([w for w in _clean_text(text).split() if w])


def _limit_words(text: str, max_words: int) -> str:
    words = [w for w in _clean_text(text).split() if w]
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


def _collapse_duplicate_tokens(text: str) -> str:
    t = _clean_text(text)
    if not t:
        return t
    # Fix common model artifacts like "e e", "de de", duplicated punctuation.
    t = re.sub(r"\b(\w+)\s+\1\b", r"\1", t, flags=re.I)
    t = re.sub(r",\s*,+", ", ", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def _looks_incomplete_pt_line(text: str) -> bool:
    t = _clean_text(text)
    if not t:
        return True
    if re.search(r"\b(e|ou|de|do|da|no|na|em|com|para|por|que)\s*$", t, flags=re.I):
        return True
    if re.search(r"\b(e|ou)\s+\1\b", t, flags=re.I):
        return True
    if re.search(r"\b(E ISSO|E AGORA|ISSO)\s*$", t, flags=re.I):
        return True
    if re.search(r"\b\w+(ando|endo|indo)\s*$", t, flags=re.I):
        return True
    if t.endswith(",") or t.endswith(".."):
        return True
    return False


def _normalize_overlay_sentence(
    text: str,
    *,
    max_words: int,
    min_words: int = 0,
    fallback_tail: str = "",
) -> str:
    words = [w for w in _collapse_duplicate_tokens(text).split() if w]
    if len(words) > max_words:
        words = words[:max_words]
    out = _trim_trailing_connectors(" ".join(words))
    out = _collapse_duplicate_tokens(out)

    if min_words > 0 and len([w for w in out.split() if w]) < min_words:
        out = _fill_to_min_words(out, min_words=min_words, fallback_tail=fallback_tail)
        out = _trim_trailing_connectors(out)
        out = _collapse_duplicate_tokens(out)

    # Remove tails that sound unfinished in overlay.
    out = re.sub(r"\b(E ISSO|E AGORA|ISSO)\s*$", "", out, flags=re.I).strip()
    out = _trim_trailing_connectors(out)
    out = _collapse_duplicate_tokens(out)
    return out.strip(" ,;:")


def _extract_story_names(text: str, *, max_names: int = 2) -> list[str]:
    candidates = re.findall(r"\b[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç]{2,}\b", _clean_text(text))
    blocked = {
        "Tres", "Três", "Gracas", "Graças", "Novela", "Reality", "Web", "Portal", "Fonte",
        "Caso", "Brasil", "Gente", "Famosos",
    }
    names: list[str] = []
    for candidate in candidates:
        if candidate in blocked:
            continue
        if candidate not in names:
            names.append(candidate)
        if len(names) >= max_names:
            break
    return names


def _pick_story_angle(item: NewsItem) -> str:
    angles = ["confronto", "consequencia", "estrategia", "reacao_publica", "virada"]
    seed = f"{item.title}|{item.link}|{item.source}"
    idx = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % len(angles)
    return angles[idx]


def _strip_title_prefix(title: str) -> str:
    t = _clean_text(title)
    if ":" in t:
        left, right = t.split(":", 1)
        if len(left.split()) <= 4:
            t = right.strip()
    return re.sub(r"\s*[-|]\s*.*$", "", t).strip()


def _first_sentence(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return _clean_text(parts[0] if parts else cleaned)


def _is_generic_overlay_line(text: str) -> bool:
    normalized = _normalize_hook_text(text)
    blocked = {
        "VIRADA INESPERADA",
        "JOGO VIROU",
        "WEB DIVIDIDA",
        "DETALHE POLEMICO",
        "CLIMA TENSO",
        "REACAO FORTE",
        "REVELACAO CHOCANTE",
    }
    return normalized in blocked


def _fill_to_min_words(text: str, *, min_words: int, fallback_tail: str) -> str:
    words = [w for w in _clean_text(text).split() if w]
    if len(words) >= min_words:
        return " ".join(words)
    tail_words = [w for w in _clean_text(fallback_tail).split() if w]
    for w in tail_words:
        words.append(w)
        if len(words) >= min_words:
            break
    return " ".join(words)


def _build_dynamic_sentence_from_item(
    item: NewsItem,
    *,
    min_words: int,
    max_words: int,
    prefer_description: bool = True,
) -> str:
    """Build a contextual sentence from title/description without fixed canned phrases."""
    title_core = _strip_title_prefix(item.title)
    desc_core = _first_sentence(_clean_description_boilerplate(item.description, title=item.title))

    parts: list[str] = []
    if prefer_description and desc_core:
        parts.append(desc_core)
    if title_core and title_core not in parts:
        parts.append(title_core)
    if (not prefer_description) and desc_core and desc_core not in parts:
        parts.append(desc_core)

    raw = " ".join(parts)
    sentence = _normalize_overlay_sentence(
        raw,
        max_words=max_words,
        min_words=min_words,
        fallback_tail=title_core or desc_core or raw,
    )

    # Final defensive normalization without injecting fixed text.
    sentence = _trim_trailing_connectors(sentence)
    sentence = _collapse_duplicate_tokens(sentence)
    words = [w for w in sentence.split() if w]
    if len(words) > max_words:
        sentence = " ".join(words[:max_words])
    return sentence.strip(" ,;:.!?")


def _build_v5_fallback_hook(item: NewsItem) -> str:
    hook = _build_dynamic_sentence_from_item(
        item,
        min_words=5,
        max_words=10,
        prefer_description=False,
    ).upper()
    hook = _smart_truncate_hook(hook, max_words=10)
    hook = _fit_hook_to_overlay(hook, max_chars=24, max_lines=3, min_words=5)
    if _looks_incomplete_pt_line(hook):
        hook = _trim_trailing_connectors(hook)
    return hook


def _build_v5_fallback_headline(item: NewsItem) -> str:
    headline = _build_dynamic_sentence_from_item(
        item,
        min_words=9,
        max_words=16,
        prefer_description=False,
    )
    return headline.rstrip(".,;:!?")


def _build_v5_fallback_body(item: NewsItem) -> str:
    body = _build_dynamic_sentence_from_item(
        item,
        min_words=14,
        max_words=24,
        prefer_description=True,
    )
    return body.rstrip(".,;:!?")


def _ensure_contextual_headline_line(headline: str, item: NewsItem) -> str:
    clean = _clean_text(headline)
    if not clean or _count_words(clean) < 7 or _is_generic_overlay_line(clean):
        return _build_v5_fallback_headline(item)
    clean = _normalize_overlay_sentence(clean, max_words=16, min_words=9, fallback_tail=item.title)
    return clean.rstrip(".,;:!?")


def _ensure_contextual_body_line(body: str, item: NewsItem) -> str:
    clean = _clean_text(body)
    if not clean or _count_words(clean) < 6 or _is_generic_overlay_line(clean):
        return _build_v5_fallback_body(item)
    clean = _normalize_overlay_sentence(
        clean,
        max_words=24,
        min_words=14,
        fallback_tail=_strip_title_prefix(item.title),
    )
    if _looks_incomplete_pt_line(clean):
        clean = _build_v5_fallback_body(item)
    return clean.rstrip(".,;:!?")


def _has_death_claim(text: str) -> bool:
    t = _normalize_hook_text(text)
    return bool(re.search(r"\b(MORRE|MORREU|MORTA|MORTO|MATA|MATOU|ASSASSIN)\b", t))


def _extract_death_target(text: str) -> str:
    clean = _clean_text(text).upper()
    m = re.search(r"\b(?:MATA|MATOU|ASSASSINA|ASSASSINOU)\s+([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]+)\b", clean)
    if not m:
        return ""
    return m.group(1).strip()


def _is_hook_inconsistent_with_story(hook: str, headline: str, body: str) -> bool:
    if not hook:
        return True
    if _has_death_claim(hook) and not (_has_death_claim(headline) or _has_death_claim(body)):
        return True
    hook_target = _extract_death_target(hook)
    body_target = _extract_death_target(body)
    if hook_target and body_target and hook_target != body_target:
        return True
    return False


def _build_tarja_text(text: str, *, item: NewsItem | None = None) -> str:
    clean = _clean_text(text)
    if not clean and item is not None:
        clean = _build_v5_fallback_body(item)
    if not clean:
        return ""
    clean = _normalize_overlay_sentence(
        clean,
        max_words=24,
        min_words=14,
        fallback_tail=_strip_title_prefix(item.title) if item else clean,
    )
    if _looks_incomplete_pt_line(clean) and item is not None:
        clean = _build_v5_fallback_body(item)
    return clean.rstrip(".,;:!?")


def _fit_lines_in_bar(
    *,
    bar_y: int,
    bar_h: int,
    line_count: int,
    target_font: int,
    min_font: int,
    gap: int = 8,
    inner_padding: int = 12,
) -> tuple[int, int, int]:
    """Return font_size, line_step and start_y fitted inside a rectangular bar."""
    count = max(1, line_count)
    usable_h = max(1, bar_h - (inner_padding * 2) - ((count - 1) * gap))
    font_size = max(min_font, min(target_font, usable_h // count))
    line_step = font_size + gap
    block_h = (font_size * count) + (gap * (count - 1))
    start_y = bar_y + max(0, (bar_h - block_h) // 2)
    return font_size, line_step, start_y


def _fit_font_to_width(
    lines: list[str],
    *,
    target_font: int,
    min_font: int,
    max_text_width_px: int,
    glyph_ratio: float = 0.56,
) -> int:
    """Approximate drawtext width fit using longest line length."""
    if not lines:
        return target_font
    longest = max(len(line) for line in lines if line)
    if longest <= 0:
        return target_font
    width_cap = int(max_text_width_px / max(1.0, longest * glyph_ratio))
    return max(min_font, min(target_font, width_cap))


def _extract_v5_lines(raw: str) -> list[str]:
    lines: list[str] = []
    for ln in str(raw or "").splitlines():
        t = ln.strip()
        if not t:
            continue
        if t.startswith("#"):
            continue
        t = re.sub(
            r"^(gancho|hook|headline|titulo|title|corpo|body|tarja|descricao|descrição|description|cta)\s*[:\-–—=]\s*",
            "",
            t,
            flags=re.I,
        ).strip()
        if t:
            lines.append(" ".join(t.split()))
    return lines[:5]


def _validate_v5_lines(lines: list[str], *, is_pt: bool) -> tuple[bool, str]:
    if len(lines) < 5:
        return False, "retornou menos de 5 linhas"

    hook, headline, body, description, cta = lines[:5]

    hook_words = _count_words(hook)
    if hook_words < 5 or hook_words > 10:
        return False, "hook fora de faixa de palavras"
    if _looks_incomplete_pt_line(hook):
        return False, "hook com final incompleto"

    headline_words = _count_words(headline)
    if headline_words < 9 or headline_words > 16:
        return False, "headline fora de faixa de palavras"

    body_words = _count_words(body)
    if body_words < 14 or body_words > 24:
        return False, "body fora de faixa de palavras"
    if _looks_incomplete_pt_line(body):
        return False, "body com final incompleto"

    if len(_split_sentences(description)) < 2:
        return False, "descricao sem duas frases"

    if "?" in cta:
        return False, "cta em formato de pergunta"

    return True, ""


def _summarize_news_text(item: NewsItem) -> str:
    is_pt = any(profile_name in item.feed_url for profile_name, _ in FEED_PROFILES["br"]) or "contigo" in item.feed_url or "ofuxico" in item.feed_url or "terra" in item.feed_url or "ig" in item.feed_url
    
    article_text = _extract_article_text(item.link)
    clean_desc = _clean_description_boilerplate(item.description, title=item.title)
    context = _clean_text(f"{item.title}. {clean_desc}. {article_text}")
    context = context[:2200]

    cfg = OpenAIConfig()
    summary_model = os.getenv("GOSSIP_SUMMARY_MODEL", cfg.model).strip()
    if is_openai_configured(cfg):
        try:
            api_key = os.getenv(cfg.api_key_env, "").strip()
            url = f"{cfg.base_url.rstrip('/')}/chat/completions"
            
            if is_pt:
                system_instr = (
                    "Voce cria textos no formato editorial Babado Rapido V5 para Shorts de fofoca.\n\n"
                    "FORMATO OBRIGATORIO: exatamente 5 linhas em texto puro (sem bullets, sem labels):\n"
                    "Linha 1 = HOOK: pergunta OU afirmacao de impacto com 5 a 10 palavras, com nome e conflito.\n"
                    "Linha 2 = HEADLINE DE APOIO: 9 a 14 palavras explicando o que aconteceu.\n"
                    "Linha 3 = BODY/TARJA: 14 a 22 palavras com contexto e consequencia clara do fato.\n"
                    "Linha 4 = DESCRICAO: 2 frases curtas interpretativas (nao literal de portal).\n"
                    "Linha 5 = CTA: chamada de engajamento curta (imperativa, sem pergunta).\n\n"
                    "Regras:\n"
                    "- Tom de reacao da web, nao manchete.\n"
                    "- Linha 1 e Linha 3 aparecem no video e precisam ter sujeito + acao + consequencia.\n"
                    "- Nao repetir o titulo literal do portal.\n"
                    "- Evite frases vazias tipo 'jogo virou', 'web dividida', 'detalhe polemico'.\n"
                    "- Escreva em portugues padrao, sem giria e sem apelido informal.\n"
                    "- Linha 1 precisa ser frase fechada e autoexplicativa.\n"
                    "- Linha 3 precisa terminar em frase completa, nunca em conectivo.\n"
                    "- Nunca termine frases com: 'e isso', 'e agora', 'vai', 'com', ou gerundio sem complemento.\n"
                    "- Zero hashtags e zero emojis.\n"
                    "- Apenas o HOOK pode vir em caixa alta total.\n"
                    "- Varie o angulo narrativo entre: confronto, consequencia, estrategia, reacao publica, virada.\n"
                    "- Nao adicione texto extra antes/depois das 5 linhas.\n"
                    "\nEXEMPLO DE REFERENCIA:\n"
                    "TEMA: Samira tenta tirar dinheiro de Arminda e o plano termina em morte.\n"
                    "HOOK: SAMIRA PRESSIONA ARMINDA E A TRETA SAI DO CONTROLE?\n"
                    "HEADLINE: Samira tenta extorquir Arminda e provoca confronto direto entre as duas.\n"
                    "BODY: Arminda reage no impulso, atira e acerta a pessoa errada.\n"
                    "DESCRICAO: O confronto cresceu rapido apos a chantagem vir a tona. A web discutiu quem cruzou primeiro o limite.\n"
                    "CTA: COMENTA O QUE ACHOU!\n"
                )
                user_content = f"Noticia:\n{context}"
            else:
                system_instr = (
                    "You create editorial Babado Rapido V5 style text for gossip shorts.\n\n"
                    "MANDATORY FORMAT: exactly 5 plain-text lines (no bullets, no labels):\n"
                    "Line 1 = HOOK: question OR impact statement in 5 to 10 words.\n"
                    "Line 2 = SUPPORT HEADLINE: 9 to 14 words explaining what happened.\n"
                    "Line 3 = BODY/TAG BAR: 14 to 22 words with context and a clear consequence.\n"
                    "Line 4 = DESCRIPTION: 2 short interpretive sentences (not literal portal text).\n"
                    "Line 5 = CTA: short imperative engagement call (not a question).\n\n"
                    "Rules:\n"
                    "- Web-reaction tone, not a newspaper headline.\n"
                    "- Line 1 and Line 3 are on-screen and must include subject + action + consequence.\n"
                    "- Do not copy source title literally.\n"
                    "- Use standard language and complete sentences.\n"
                    "- Line 1 must be a closed and self-contained sentence.\n"
                    "- Never end Line 3 with dangling connectors or unfinished clauses.\n"
                    "- Avoid empty generic phrases like 'game changed' or 'internet divided'.\n"
                    "- Zero hashtags and zero emojis.\n"
                    "- Only HOOK may be fully uppercase.\n"
                    "- Output only the 5 lines.\n"
                )
                user_content = f"News:\n{context}"

            messages = [
                {"role": "system", "content": system_instr},
                {"role": "user", "content": user_content},
            ]
            for _ in range(3):
                payload = {
                    "model": summary_model,
                    "temperature": 0.45,
                    "max_completion_tokens": 260,
                    "messages": messages,
                }
                r = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=60,
                )
                if r.status_code >= 400:
                    break
                data = r.json()
                content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
                if not content:
                    break

                lines = _extract_v5_lines(str(content))
                valid, reason = _validate_v5_lines(lines, is_pt=is_pt)
                if valid:
                    return "\n".join(lines[:5])

                messages.append({"role": "assistant", "content": str(content)})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Refaça do zero mantendo o formato de 5 linhas. Corrija este erro: {reason}. "
                            "Não deixe nenhuma frase truncada."
                        ),
                    }
                )
        except Exception:
            pass

    # Local fallback: build contextual lines from title/description (no canned templates).
    title = _clean_text(item.title) or _clean_text(item.description) or "noticia em atualizacao"
    fallback_hook = _build_v5_fallback_hook(item).upper()
    headline_base = _build_v5_fallback_headline(item)
    body_base = _build_v5_fallback_body(item)
    desc_line_1 = _build_dynamic_sentence_from_item(item, min_words=9, max_words=16, prefer_description=False)
    desc_line_2 = _build_dynamic_sentence_from_item(item, min_words=9, max_words=16, prefer_description=True)
    if _normalize_hook_text(desc_line_1) == _normalize_hook_text(desc_line_2):
        desc_line_2 = _build_dynamic_sentence_from_item(item, min_words=10, max_words=18, prefer_description=True)
    desc_base = f"{desc_line_1}. {desc_line_2}."
    return "\n".join(
        [
            fallback_hook,
            headline_base,
            body_base,
            desc_base,
            _get_random_cta(title, headline=title),
        ]
    )


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
    hook_font = _ffmpeg_escape(_select_hook_font())
    body_font = _ffmpeg_escape(_select_body_font())
    fade_out_start = max(0.0, duration_s - 1.2)
    (out_video.parent / "_overlay_text").mkdir(parents=True, exist_ok=True)

    main_path = summary_file or headline_file
    body_raw = main_path.read_text(encoding="utf-8") if main_path.exists() else ""
    body_clean = _sanitize_overlay_text(body_raw).replace("\xa0", " ")
    hook_raw = hook_file.read_text(encoding="utf-8") if hook_file and hook_file.exists() else ""
    hook_clean = _sanitize_overlay_text(hook_raw).replace("\xa0", " ")
    headline_raw = headline_file.read_text(encoding="utf-8") if headline_file.exists() else ""
    headline_clean = _sanitize_overlay_text(headline_raw).replace("\xa0", " ")

    if not hook_clean:
        hook_clean = _build_v5_fallback_hook(
            NewsItem(
                source=source,
                feed_url="",
                title=headline_clean or "Caso em destaque",
                link="",
                published="",
                image_url="",
                description=body_clean,
            )
        )

    tarja_text = _build_tarja_text(body_clean)
    hook_lines = textwrap.wrap(hook_clean.upper(), width=30, break_long_words=False, break_on_hyphens=False)[:2]
    tarja_lines = textwrap.wrap(tarja_text.upper(), width=27, break_long_words=False, break_on_hyphens=False)[:4]
    if not hook_lines:
        hook_seed = _clean_text(headline_clean or body_clean or "noticia em destaque")
        hook_lines = textwrap.wrap(_fit_hook_to_overlay(hook_seed.upper(), max_chars=24, max_lines=3, min_words=3), width=30, break_long_words=False, break_on_hyphens=False)[:2] or ["NOTICIA EM DESTAQUE"]
    if not tarja_lines:
        tarja_seed = _clean_text(body_clean or headline_clean or "noticia em atualizacao")
        tarja_lines = textwrap.wrap(tarja_seed.upper(), width=27, break_long_words=False, break_on_hyphens=False)[:4] or ["NOTICIA EM ATUALIZACAO"]

    TOP_PANEL_Y = 0
    TOP_PANEL_H = 610
    HOOK_AREA_Y = 450
    HOOK_AREA_H = 170
    BOTTOM_PANEL_Y = 1290
    BOTTOM_PANEL_H = 300
    LOGO_Y = 120
    BODY_LEFT_X = 56

    hook_size, hook_step, hook_start_y = _fit_lines_in_bar(
        bar_y=HOOK_AREA_Y,
        bar_h=HOOK_AREA_H,
        line_count=len(hook_lines),
        target_font=92,
        min_font=54,
        gap=8,
        inner_padding=18,
    )
    hook_size = _fit_font_to_width(
        hook_lines,
        target_font=hook_size,
        min_font=54,
        max_text_width_px=920,
    )
    hook_step = hook_size + 8
    hook_block_h = (hook_size * max(1, len(hook_lines))) + (8 * max(0, len(hook_lines) - 1))
    hook_start_y = HOOK_AREA_Y + max(0, (HOOK_AREA_H - hook_block_h) // 2)

    tarja_size, tarja_step, tarja_start_y = _fit_lines_in_bar(
        bar_y=BOTTOM_PANEL_Y,
        bar_h=BOTTOM_PANEL_H,
        line_count=max(1, len(tarja_lines)),
        target_font=56,
        min_font=34,
        gap=6,
        inner_padding=22,
    )
    tarja_size = _fit_font_to_width(
        tarja_lines,
        target_font=tarja_size,
        min_font=34,
        max_text_width_px=940,
    )
    tarja_step = tarja_size + 6
    tarja_block_h = (tarja_size * max(1, len(tarja_lines))) + (6 * max(0, len(tarja_lines) - 1))
    tarja_start_y = BOTTOM_PANEL_Y + max(0, (BOTTOM_PANEL_H - tarja_block_h) // 2)

    text_layers = [
        f"drawbox=x=0:y={TOP_PANEL_Y}:w=1080:h={TOP_PANEL_H}:color=black@1.0:t=fill",
        f"drawbox=x=0:y={BOTTOM_PANEL_Y}:w=1080:h={BOTTOM_PANEL_H}:color=black@0.96:t=fill",
    ]
    for i, line in enumerate(hook_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = hook_start_y + (i * hook_step)
        text_layers.append(
            f"drawtext=text='{line_esc}':fontfile='{hook_font}':fontcolor=white:"
            f"fontsize={hook_size}:borderw=2:bordercolor=black@0.88:"
            "shadowcolor=black@0.30:shadowx=0:shadowy=2:"
            f"x=(w-tw)/2:y={y_pos}"
        )

    for i, line in enumerate(tarja_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = tarja_start_y + (i * tarja_step)
        text_layers.append(
            f"drawtext=text='{line_esc}':fontfile='{body_font}':fontcolor=white:"
            f"fontsize={tarja_size}:borderw=1:bordercolor=black@0.82:shadowcolor=black@0.24:shadowx=0:shadowy=1:"
            f"x={BODY_LEFT_X}:y={y_pos}"
        )

    # Mantem enquadramento sem crop para respeitar o fit no template.
    vf_layers = [
        "scale=1080:1920:force_original_aspect_ratio=decrease",
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0B0B0B",
        "setsar=1",
        "format=yuv420p",
        *text_layers,
    ]
    vf = ",".join(vf_layers)

    out_video.parent.mkdir(parents=True, exist_ok=True)

    if logo_path is not None and logo_path.exists():
        overlay_graph = (
            f"[0:v]{vf}[bg];"
            "[1:v]scale=300:-1:flags=lanczos[logo];"
            f"[bg][logo]overlay=(W-w)/2:{LOGO_Y}[v]"
        )

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
            overlay_graph,
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
    hook_font = _ffmpeg_escape(_select_hook_font())
    body_font = _ffmpeg_escape(_select_body_font())

    main_path = summary_file or headline_file
    body_raw = main_path.read_text(encoding="utf-8") if main_path.exists() else ""
    body_clean = _sanitize_overlay_text(body_raw).replace("\xa0", " ")
    hook_raw = hook_file.read_text(encoding="utf-8") if hook_file and hook_file.exists() else ""
    hook_clean = _sanitize_overlay_text(hook_raw).replace("\xa0", " ")
    headline_raw = headline_file.read_text(encoding="utf-8") if headline_file.exists() else ""
    headline_clean = _sanitize_overlay_text(headline_raw).replace("\xa0", " ")
    if not hook_clean:
        hook_clean = _build_v5_fallback_hook(
            NewsItem(
                source=source,
                feed_url="",
                title=headline_clean or "Caso em destaque",
                link="",
                published="",
                image_url="",
                description=body_clean,
            )
        )

    tarja_text = _build_tarja_text(body_clean)
    hook_lines = textwrap.wrap(hook_clean.upper(), width=30, break_long_words=False, break_on_hyphens=False)[:2]
    tarja_lines = textwrap.wrap(tarja_text.upper(), width=27, break_long_words=False, break_on_hyphens=False)[:4]
    if not hook_lines:
        hook_seed = _clean_text(headline_clean or body_clean or "noticia em destaque")
        hook_lines = textwrap.wrap(_fit_hook_to_overlay(hook_seed.upper(), max_chars=24, max_lines=3, min_words=3), width=30, break_long_words=False, break_on_hyphens=False)[:2] or ["NOTICIA EM DESTAQUE"]
    if not tarja_lines:
        tarja_seed = _clean_text(body_clean or headline_clean or "noticia em atualizacao")
        tarja_lines = textwrap.wrap(tarja_seed.upper(), width=27, break_long_words=False, break_on_hyphens=False)[:4] or ["NOTICIA EM ATUALIZACAO"]

    TOP_PANEL_Y = 0
    TOP_PANEL_H = 610
    HOOK_AREA_Y = 450
    HOOK_AREA_H = 170
    BOTTOM_PANEL_Y = 1290
    BOTTOM_PANEL_H = 300
    LOGO_Y = 120
    BODY_LEFT_X = 56

    hook_size, hook_step, hook_start_y = _fit_lines_in_bar(
        bar_y=HOOK_AREA_Y,
        bar_h=HOOK_AREA_H,
        line_count=len(hook_lines),
        target_font=92,
        min_font=54,
        gap=8,
        inner_padding=18,
    )
    hook_size = _fit_font_to_width(
        hook_lines,
        target_font=hook_size,
        min_font=54,
        max_text_width_px=920,
    )
    hook_step = hook_size + 8
    hook_block_h = (hook_size * max(1, len(hook_lines))) + (8 * max(0, len(hook_lines) - 1))
    hook_start_y = HOOK_AREA_Y + max(0, (HOOK_AREA_H - hook_block_h) // 2)

    tarja_size, tarja_step, tarja_start_y = _fit_lines_in_bar(
        bar_y=BOTTOM_PANEL_Y,
        bar_h=BOTTOM_PANEL_H,
        line_count=max(1, len(tarja_lines)),
        target_font=56,
        min_font=34,
        gap=6,
        inner_padding=22,
    )
    tarja_size = _fit_font_to_width(
        tarja_lines,
        target_font=tarja_size,
        min_font=34,
        max_text_width_px=940,
    )
    tarja_step = tarja_size + 6
    tarja_block_h = (tarja_size * max(1, len(tarja_lines))) + (6 * max(0, len(tarja_lines) - 1))
    tarja_start_y = BOTTOM_PANEL_Y + max(0, (BOTTOM_PANEL_H - tarja_block_h) // 2)

    text_filters = [
        f"drawbox=x=0:y={TOP_PANEL_Y}:w=1080:h={TOP_PANEL_H}:color=black@1.0:t=fill",
        f"drawbox=x=0:y={BOTTOM_PANEL_Y}:w=1080:h={BOTTOM_PANEL_H}:color=black@0.96:t=fill",
    ]
    for i, line in enumerate(hook_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = hook_start_y + (i * hook_step)
        text_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{hook_font}':fontcolor=white:"
            f"fontsize={hook_size}:borderw=2:bordercolor=black@0.88:"
            "shadowcolor=black@0.30:shadowx=0:shadowy=2:"
            f"x=(w-tw)/2:y={y_pos}"
        )

    for i, line in enumerate(tarja_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = tarja_start_y + (i * tarja_step)
        text_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{body_font}':fontcolor=white:"
            f"fontsize={tarja_size}:borderw=1:bordercolor=black@0.82:shadowcolor=black@0.24:shadowx=0:shadowy=1:"
            f"x={BODY_LEFT_X}:y={y_pos}"
        )

    scale_filters = [
        "scale=1080:1920:force_original_aspect_ratio=decrease",
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0B0B0B",
        "setsar=1",
        "format=yuv420p",
    ]

    out_video.parent.mkdir(parents=True, exist_ok=True)

    if logo_path is not None and logo_path.exists():
        base_filters = ",".join(scale_filters)
        text_only = ",".join(text_filters)
        overlay_graph = (
            f"[0:v]{base_filters},{text_only}[bg];"
            "[1:v]scale=300:-1:flags=lanczos[logo];"
            f"[bg][logo]overlay=(W-w)/2:{LOGO_Y}[v]"
        )
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
            overlay_graph,
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


def create_post_for_item(item: NewsItem, args: argparse.Namespace) -> bool:
    """Função centralizada para criar um post a partir de um NewsItem."""
    root = Path(__file__).resolve().parents[1]
    post_dir = root / "gossip_post"
    post_dir.mkdir(parents=True, exist_ok=True)
    hook_history_path = post_dir / HOOK_HISTORY_FILE

    try:
        image_path = _download_image(item.image_url, post_dir / "news_image")
        # Padrao VN: sem moldura decorativa, mantendo look limpo preto + logo + texto.
        render_image_path = image_path

        # ── Parse da IA: formato V5 (hook / headline / body / descricao) ──
        raw_script = _summarize_news_text(item)
        all_lines = [ln.rstrip() for ln in raw_script.splitlines()]

        # Separa hashtags residuais (caso a IA insira mesmo assim)
        hashtags = " ".join([ln.lower() for ln in all_lines if ln.strip().startswith("#")])

        # Limpa: remove hashtags, labels, linhas vazias e separadores
        content_lines: list[str] = []
        parsed_fields: dict[str, str] = {}
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
            labeled = re.match(
                r"^(gancho|hook|headline|titulo|title|corpo|body|tarja|descricao|descrição|description|cta)\s*[:\-–—=]\s*(.+)$",
                stripped,
                flags=re.I,
            )
            if labeled:
                key = labeled.group(1).lower()
                value = labeled.group(2).strip()
                if key in {"gancho", "hook"}:
                    parsed_fields["hook"] = value
                elif key in {"headline", "titulo", "title"}:
                    parsed_fields["headline"] = value
                elif key in {"corpo", "body", "tarja"}:
                    parsed_fields["body"] = value
                elif key in {"descricao", "descrição", "description"}:
                    parsed_fields["description"] = value
                elif key == "cta":
                    parsed_fields["cta"] = value
                continue

            cleaned = re.sub(r"^(linha|line)\s*\d*\s*[:\-–—=]\s*", "", stripped, flags=re.I).strip()
            if cleaned:
                content_lines.append(cleaned)

        ai_cta = parsed_fields.get("cta", "")
        hook = parsed_fields.get("hook", "")
        headline_core = parsed_fields.get("headline", "")
        body = parsed_fields.get("body", "")
        description_text = parsed_fields.get("description", "")

        if not hook and content_lines:
            hook = content_lines[0]
        if not headline_core and len(content_lines) > 1:
            headline_core = content_lines[1]
        if not body and len(content_lines) > 2:
            body = content_lines[2]
        if not description_text and len(content_lines) > 3:
            description_text = content_lines[3]
        if not ai_cta and len(content_lines) > 4:
            ai_cta = content_lines[4]

        if not hook:
            hook = _build_v5_fallback_hook(item)
        if not headline_core:
            headline_core = _build_v5_fallback_headline(item)
        if not body:
            body = _build_v5_fallback_body(item)
        if not description_text:
            description_text = f"{_clean_text(item.title)}. A web reagiu e as opinioes ficaram divididas."

        # ── Limpeza leve (sem truncamento agressivo) ──
        # Remove hashtags residuais e caracteres problemáticos, preserva pontuação
        hook_clean = re.sub(r'#\w+', '', hook).strip()
        hook_clean = re.sub(r"[^\w\s\u00C0-\u00FF?!]", '', hook_clean)
        hook_clean = re.sub(r'\s+', ' ', hook_clean).strip()
        recent_hooks = _load_recent_hook_history(hook_history_path, window=HOOK_HISTORY_WINDOW)

        ai_hook = _generate_contextual_hook_with_ai(item, recent_hooks, fallback=hook_clean)
        if ai_hook:
            hook_clean = ai_hook

        if _is_probably_bad_hook(hook_clean):
            hook_clean = _build_v5_fallback_hook(item)
        hook_clean = _smart_truncate_hook(hook_clean, max_words=10)
        # Encaixa no overlay sem cortar palavras finais.
        hook_clean = _fit_hook_to_overlay(hook_clean, max_chars=24, max_lines=3, min_words=5)
        if _is_overgeneric_hook(hook_clean):
            ai_retry = _generate_contextual_hook_with_ai(item, recent_hooks, fallback=hook_clean)
            if ai_retry:
                hook_clean = ai_retry
        if _is_probably_bad_hook(hook_clean):
            hook_clean = _build_v5_fallback_hook(item)
        hook_clean = _trim_trailing_connectors(hook_clean)
        hook_clean = _smart_truncate_hook(hook_clean, max_words=10)
        hook_clean = _fit_hook_to_overlay(hook_clean, max_chars=24, max_lines=3, min_words=5)
        headline_text_clean = re.sub(r'#\w+', '', headline_core).strip()
        headline_text_clean = re.sub(r"[^\w\s\u00C0-\u00FF.,;:?!-]", "", headline_text_clean)
        headline_text_clean = re.sub(r"\s+", " ", headline_text_clean).strip()
        headline = _enforce_editorial_headline(headline_text_clean, item.title)
        headline = _ensure_contextual_headline_line(headline, item)

        body_text_clean = re.sub(r'#\w+', '', body).strip()
        body_text_clean = re.sub(r"[^\w\s\u00C0-\u00FF.,;:?!-]", "", body_text_clean)
        body_text_clean = re.sub(r"\s+", " ", body_text_clean).strip()
        body_text_clean = _ensure_contextual_body_line(body_text_clean, item)
        body_text_clean = _rewrite_overlay_body_if_needed(body_text_clean, item=item)
        body_text_clean = _build_tarja_text(body_text_clean, item=item)
        if _looks_incomplete_pt_line(body_text_clean):
            body_text_clean = _build_tarja_text(_build_v5_fallback_body(item), item=item)
        if _is_hook_inconsistent_with_story(hook_clean, headline, body_text_clean):
            hook_clean = _build_v5_fallback_hook(item)
            hook_clean = _smart_truncate_hook(hook_clean, max_words=10)
            hook_clean = _fit_hook_to_overlay(hook_clean, max_chars=24, max_lines=3, min_words=5)

        description_text_clean = re.sub(r'#\w+', '', description_text).strip()
        description_text_clean = re.sub(r"[^\w\s\u00C0-\u00FF.,!?]", "", description_text_clean)
        description_text_clean = re.sub(r"\s+", " ", description_text_clean).strip()
        desc_line_1, desc_line_2 = _build_editorial_description(description_text_clean, item)
        description_text_clean = f"{desc_line_1} {desc_line_2}".strip()
        description_multiline = f"{desc_line_1}\n{desc_line_2}"

        # Hook: 24 chars por linha, máximo 3 linhas (evita cortar contexto no topo)
        hook_wrapped = _wrap_for_overlay(hook_clean, max_chars=24, max_lines=3, upper=True)
        
        hook_file = post_dir / "hook.txt"
        hook_file.write_text(_sanitize_overlay_text(hook_wrapped) + "\n", encoding="utf-8")
        _save_hook_to_history(hook_history_path, hook_clean, title=item.title, source=item.source)

        summary_file = post_dir / "summary.txt"
        summary_file.write_text(_sanitize_overlay_text(body_text_clean) + "\n", encoding="utf-8")

        headline_file = post_dir / "headline.txt"
        headline_file.write_text(_sanitize_overlay_text(headline) + "\n", encoding="utf-8")
        image_duration_s = 11.0

        # Keep source metadata for traceability and later automation.
        metadata = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": item.source,
            "feed_url": item.feed_url,
            "title": item.title,
            "article_url": item.link,
            "published": item.published,
            "image_url": item.image_url,
            "description": item.description,
            "local_image": str(image_path.relative_to(root)),
            "render_image": str(render_image_path.relative_to(root)) if render_image_path.exists() else str(image_path.relative_to(root)),
            "video_duration_s": image_duration_s,
            "hook": hook_clean,
            "headline": headline,
            "body": body_text_clean,
            "description_overlay": description_text_clean,
        }
        (post_dir / "news.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # Caption com hashtags (para redes sociais)
        # Usa descrição interpretativa fora do vídeo + hashtags separadas no final
        (post_dir / "caption.txt").write_text(
            f"{hook_clean}\n{description_multiline}\n\n{hashtags}\n\nFonte: {item.source.upper()}\nLink: {item.link}\n",
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
            cta_text = _sanitize_cta_text(_get_random_cta(item.title, headline=item.title))
        
        logo_path = None
        if args.logo:
            logo_path = Path(args.logo).expanduser().resolve()
        else:
            for name in ("logo.png", "logo.webp", "logo.jpg", "logo.jpeg"):
                candidate = post_dir / name
                if candidate.exists():
                    logo_path = candidate
                    break
            if logo_path is None:
                candidate = root / "assets" / "Logo" / "logo.png"
                if candidate.exists():
                    logo_path = candidate

        _render_short(
            render_image_path,
            headline_file,
            item.source,
            output_video,
            hook_file=hook_file,
            summary_file=summary_file,
            cta_text=cta_text,
            logo_path=logo_path,
            duration_s=image_duration_s,
        )

        artifact_payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "title": item.title,
            "source": item.source,
            "article_url": item.link,
            "video_path": str(output_video.relative_to(root)),
            "duration_s": image_duration_s,
            "hook": hook_clean,
            "headline": headline,
            "body": body_text_clean,
            "description_line_1": desc_line_1,
            "description_line_2": desc_line_2,
            "cta": cta_text,
        }
        artifact_json = output_video.with_suffix(".json")
        artifact_json.write_text(json.dumps(artifact_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # Adiciona um pequeno delay para garantir que o arquivo de vídeo seja liberado pelo SO
        import time
        time.sleep(1)

        # Telegram Notification with hashtags in caption
        # Clean up hook and headline for better formatting (já estão limpos, sem hashtags)
        hook_telegram = " ".join(hook_clean.split())  # Remove extra spaces/newlines
        headline_telegram = " ".join(description_text_clean.split())  # Single line
        
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
