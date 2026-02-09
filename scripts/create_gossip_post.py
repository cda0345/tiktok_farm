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
    """Pick a bold/condensed font.

    Priority:
    1) Repo-bundled font(s) (works on GitHub Actions/Linux)
    2) System fonts (macOS/local dev)
    """
    repo_fonts = [
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
    text = (text or "").replace("\r", "")
    # Remove caracteres Unicode problemáticos e invisíveis
    text = re.sub(r"[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]", "", text)
    # Remove emojis e símbolos especiais que podem causar problemas
    text = re.sub(r'[\U0001F300-\U0001F9FF]', '', text)  # Emojis
    text = re.sub(r'[\u2600-\u26FF\u2700-\u27BF]', '', text)  # Dingbats e símbolos
    # Normaliza espaços em branco
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove caracteres de controle problemáticos
    text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')
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
    # Use break_long_words=False para evitar cortar palavras no meio
    wrapped = textwrap.wrap(clean, width=max_chars, break_long_words=False, break_on_hyphens=False)
    # We prioritize showing the full message without "..." suffixes
    return "\n".join(wrapped[:max_lines])


def _pick_pt_hook(headline: str) -> str:
    h = _clean_text(headline).lower()
    if any(k in h for k in ["morre", "morte", "luto", "velório", "velorio", "enterro"]):
        return "LUTO NO MUNDO FAMOSO"
    if any(k in h for k in ["bbb", "big brother", "paredão", "paredao", "eliminação", "eliminacao", "prova do líder", "prova do lider", "anjo"]):
        return "TRETA NO BBB"
    if any(k in h for k in ["a fazenda", "reality", "peão", "peao"]):
        return "TRETA NO REALITY"
    if any(k in h for k in ["filha", "filho", "bebê", "bebe", "gravidez", "grávida", "gravida", "nasceu"]):
        return "FOFURA E EMOÇÃO"
    if any(k in h for k in ["separ", "divórcio", "divorcio", "trai", "affair", "corno"]):
        return "SEPARAÇÃO CONFIRMADA"
    if any(k in h for k in ["polêmica", "polemica", "briga", "treta", "confusão", "confusao", "desabaf"]):
        return "DEU O QUE FALAR"
    if any(k in h for k in ["novela", "personagem", "ator", "atriz", "papel", "cena"]):
        return "BABADO NA NOVELA"
    if any(k in h for k in ["cirurgia", "hospital", "internado", "internada", "saúde", "saude", "doença", "doenca"]):
        return "NOTÍCIA URGENTE"
    if any(k in h for k in ["namoro", "casal", "romance", "casamento", "noivar", "noivo", "noiva"]):
        return "ROMANCE CONFIRMADO"
    if any(k in h for k in ["carnaval", "bloco", "fantasia", "desfile"]):
        return "BABADO NO CARNAVAL"
    return "FOFOCA DO MOMENTO"


def _pick_en_hook(headline: str) -> str:
    h = _clean_text(headline).lower()
    if any(k in h for k in ["dies", "death", "dead", "passed away", "funeral"]):
        return "SHOCKING LOSS"
    if any(k in h for k in ["split", "divorce", "cheat", "scandal", "affair"]):
        return "MAJOR CELEB DRAMA"
    if any(k in h for k in ["baby", "pregnan", "daughter", "son", "born"]):
        return "BIG FAMILY UPDATE"
    if any(k in h for k in ["arrest", "jail", "court", "lawsuit", "sued"]):
        return "CELEB IN TROUBLE"
    if any(k in h for k in ["wedding", "engaged", "dating", "romance", "couple"]):
        return "LOVE CONFIRMED"
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
    is_pt = _is_portuguese_context(source, clean)

    # Hook: sempre usar chamada temática impactante (estilo TikTok/Shorts)
    hook_text = _pick_pt_hook(clean) if is_pt else _pick_en_hook(clean)
    hook = _wrap_for_overlay(hook_text, max_chars=20, max_lines=2, upper=True)

    # Bottom text: texto completo sem truncar — a renderização cuida do limite visual
    summary = clean
    return hook, summary


def _headline_for_overlay(headline: str, max_chars: int = 24, max_lines: int = 5) -> str:
    # Backward-compat helper for scripts that still call this.
    return _wrap_for_overlay(headline, max_chars=max_chars, max_lines=max_lines, upper=True)


def _build_display_headline(headline: str) -> str:
    # Portal-style, bold and concise.
    # Aumentado para 22 chars por linha e 7 linhas para acomodar notícias longas
    return _wrap_for_overlay(headline, max_chars=22, max_lines=7, upper=True)


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
                    "1. GANCHO (HOOK): EXATAMENTE 3-4 PALAVRAS que capturam o CLÍMAX da notícia, TUDO EM MAIÚSCULAS, SEM PONTUAÇÃO.\n"
                    "   Exemplos: 'POLÊMICA NO BBB', 'FAMOSA GRÁVIDA', 'SEPARAÇÃO CONFIRMADA', 'DECLARAÇÃO EMOCIONANTE'\n"
                    "2. RESUMO: Em UM ÚNICO PARÁGRAFO de 12-15 PALAVRAS, resuma a notícia completa mantendo a informação principal.\n"
                    "   Seja DIRETO e INFORMATIVO. Use linguagem simples. TUDO EM MAIÚSCULAS.\n"
                    "   NÃO divida em múltiplas frases. APENAS UM PARÁGRAFO corrido.\n"
                    "   Exemplo: 'CLAUDIA RODRIGUES FAZ DECLARAÇÃO EMOCIONANTE PARA ESPOSA NO ANIVERSÁRIO DE CASAMENTO'\n"
                    "3. CTA (CALL TO ACTION): Uma pergunta ou frase BEM CURTA (4-6 PALAVRAS) relacionada à notícia, TUDO EM MAIÚSCULAS.\n"
                    "   Exemplos: 'E AÍ O QUE ACHOU?', 'VOCÊ SABIA DISSO?', 'O QUE VOCÊ ACHA?', 'JÁ CONHECIA ESSA?', 'COMENTA AÍ EMBAIXO!'\n"
                    "   Deve ser RELEVANTE ao contexto da notícia. Não use CTAs genéricos sempre.\n"
                    "4. HASHTAGS: 3 hashtags relevantes em LETRAS MINÚSCULAS.\n"
                    "FORMATO FINAL (4 linhas):\n"
                    "Linha 1: Hook (3-4 palavras)\n"
                    "Linha 2: Resumo (12-15 palavras em um parágrafo)\n"
                    "Linha 3: CTA (4-6 palavras)\n"
                    "Linha 4: Hashtags (lowercase)\n"
                    "IMPORTANTE: SEM aspas, emojis, símbolos especiais ou caracteres estranhos. Apenas texto limpo."
                )
                user_content = f"Resuma esta notícia de forma DIRETA e COMPLETA:\n\n{context}"
            else:
                system_instr = (
                    "You are a Shorts/TikTok editor specialized in celebrity gossip. "
                    "MANDATORY RULES:\n"
                    "1. HOOK: EXACTLY 3-4 WORDS capturing the CLIMAX, ALL CAPS, NO PUNCTUATION.\n"
                    "   Examples: 'CELEB DIVORCE CONFIRMED', 'SHOCKING ANNOUNCEMENT', 'MAJOR CONTROVERSY', 'EMOTIONAL DECLARATION'\n"
                    "2. SUMMARY: In ONE SINGLE PARAGRAPH of 12-15 WORDS, summarize the complete news keeping the main information.\n"
                    "   Be DIRECT and INFORMATIVE. Use simple language. ALL CAPS.\n"
                    "   DO NOT split into multiple sentences. JUST ONE flowing paragraph.\n"
                    "   Example: 'CELEB SHARES EMOTIONAL TRIBUTE TO SPOUSE ON WEDDING ANNIVERSARY WITH HEARTFELT PHOTOS'\n"
                    "3. CTA (CALL TO ACTION): A VERY SHORT question or phrase (4-6 WORDS) related to the news, ALL CAPS.\n"
                    "   Examples: 'WHAT DO YOU THINK?', 'DID YOU KNOW THIS?', 'YOUR THOUGHTS BELOW?', 'COMMENT YOUR OPINION!'\n"
                    "   Must be RELEVANT to the news context. Don't always use generic CTAs.\n"
                    "4. HASHTAGS: 3 relevant hashtags in lowercase.\n"
                    "FINAL FORMAT (4 lines):\n"
                    "Line 1: Hook (3-4 words)\n"
                    "Line 2: Summary (12-15 words in one paragraph)\n"
                    "Line 3: CTA (4-6 words)\n"
                    "Line 4: Hashtags (lowercase)\n"
                    "IMPORTANT: NO quotes, emojis or special characters. Clean text only."
                )
                user_content = f"Summarize this news DIRECTLY and COMPLETELY:\n\n{context}"

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

    # YouTube Shorts safe areas (1080x1920):
    # - Keep clear of top UI + logo
    # - Keep clear of bottom UI (channel bar/buttons)
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
        y_pos = _clamp(hook_base_y + (i * 90), SAFE_TOP, SAFE_BOTTOM)
        hook_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize=72:fix_bounds=1:"
            f"box=1:boxcolor={hook_box_color}@0.96:boxborderw=20:"
            f"x=(w-tw)/2:y={y_pos}"
        )

    # Render MAIN HEADLINE
    main_input = " ".join(main_clean.split())
    main_lines = textwrap.wrap(main_input, width=22, break_long_words=False, break_on_hyphens=False)[:7]
    main_filters = []

    # Compute top of the lower text block so it never overlaps YouTube bottom UI.
    # We anchor the last line to SAFE_BOTTOM and build upwards.
    if len(main_lines) > 5:
        line_spacing = 78
        font_size = 58
    else:
        line_spacing = 85
        font_size = 62

    # Start Y so that the full block ends at SAFE_BOTTOM.
    block_h = max(0, (len(main_lines) - 1) * line_spacing)
    start_y = _clamp(SAFE_BOTTOM - block_h, SAFE_TOP + 520, SAFE_BOTTOM)

    for i, line in enumerate(main_lines):
        line_esc = _ffmpeg_escape_text(line)
        y_pos = _clamp(start_y + (i * line_spacing), SAFE_TOP, SAFE_BOTTOM)
        main_filters.append(
            f"drawtext=text='{line_esc}':fontfile='{font}':"
            f"fontcolor=white:fontsize={font_size}:fix_bounds=1:"
            f"x=(w-tw)/2:y={y_pos}"
        )

    vf_layers = [
        "scale=1080:1920:force_original_aspect_ratio=decrease",
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
        "eq=brightness=-0.02:contrast=1.08:saturation=1.02",
        *hook_filters,
        # Keep the tarjas, but ensure they start below the hook area visually.
        "drawbox=x=0:y=ih*0.56:w=iw:h=ih*0.44:color=black@0.22:t=fill",
        "drawbox=x=0:y=ih*0.66:w=iw:h=ih*0.34:color=black@0.42:t=fill",
        "drawbox=x=0:y=ih*0.76:w=iw:h=ih*0.24:color=black@0.62:t=fill",
        *main_filters,
        # CTA stays above bottom UI
        f"drawtext=text='{cta_escaped}':fontfile='{font}':fontcolor=white@0.88:"
        "fontsize=44:x=(w-text_w)/2:y=h*0.90:enable='lt(mod(t\\,1.4)\\,0.7)'",
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
        
        if len(ai_parts) >= 3:
            # Novo formato: Linha 1 = Hook, Linha 2 = Resumo, Linha 3 = CTA
            hook_raw = ai_parts[0]
            hook_words = hook_raw.split()[:4]  # Força máximo de 4 palavras
            hook = " ".join(hook_words)
            
            # Resumo: já vem completo em um parágrafo de 12-15 palavras
            resumo = ai_parts[1] if len(ai_parts) > 1 else ""
            
            # CTA: pergunta/frase curta de 4-6 palavras
            cta = ai_parts[2] if len(ai_parts) > 2 else ""
            
            # Junta Resumo + CTA para formar o headline completo
            headline_text = f"{resumo}. {cta}" if cta else resumo
        elif len(ai_parts) >= 2:
            # Fallback: se não tiver CTA, usa apenas Hook + Resumo
            hook_raw = ai_parts[0]
            hook_words = hook_raw.split()[:4]
            hook = " ".join(hook_words)
            headline_text = ai_parts[1]
        else:
            # Fallback completo: cria hook curto e impactante do título
            hook, summary = _build_text_layers(item.title, item.source)
            # Força máximo de 4 palavras no hook
            hook_words = hook.split()[:4]
            hook = " ".join(hook_words)
            headline_text = summary

        # IMPORTANTE: Remove TODAS as hashtags e caracteres especiais
        # Hashtags devem aparecer SOMENTE na caption/legenda
        hook_clean = re.sub(r'#\w+', '', hook).strip()
        hook_clean = re.sub(r'[^\w\s\u00C0-\u00FF]', '', hook_clean)  # Remove caracteres especiais exceto letras acentuadas
        hook_clean = re.sub(r'\s+', ' ', hook_clean).strip()
        
        headline_text_clean = re.sub(r'#\w+', '', headline_text).strip()
        headline_text_clean = re.sub(r'[^\w\s\u00C0-\u00FF.,!?]', '', headline_text_clean)  # Mantém pontuação básica
        headline_text_clean = re.sub(r'\s+', ' ', headline_text_clean).strip()
        
        # Limita a 21 palavras (15 do resumo + 6 do CTA = ideal para o formato completo)
        words = headline_text_clean.split()
        if len(words) > 21:
            headline_text_clean = " ".join(words[:21]) + "..."
        
        # Força caixa alta no corpo/headline
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
    p.add_argument("--logo", default="", help="Optional logo path (png/webp/jpg).")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    feeds = FEED_PROFILES[args.profile]
    item = _fetch_first_news(feeds)
    create_post_for_item(item, args)


if __name__ == "__main__":
    main()
