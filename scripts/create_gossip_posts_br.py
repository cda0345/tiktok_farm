#!/usr/bin/env python3
"""Generate multiple gossip shorts from Brazilian gossip/celebrity sites."""

from __future__ import annotations

import importlib.util
import json
import mimetypes
import random
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


BR_GOSSIP_FEEDS = [
    ("contigo", "https://contigo.com.br/feed"),
    ("ofuxico", "https://ofuxico.com.br/wp-json/wp/v2/posts?per_page=10&_embed=1"),
    ("terra_gente", "https://www.terra.com.br/diversao/gente/rss.xml"),
    ("ig_gente", "https://gente.ig.com.br/rss.xml"),
    ("hugo_gloss", "https://hugogloss.uol.com.br/feed"),
    ("metropoles", "https://www.metropoles.com/colunas/leo-dias/feed"),
]


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _load_base_module(root: Path):
    mod_path = root / "scripts" / "create_gossip_post.py"
    spec = importlib.util.spec_from_file_location("create_gossip_post", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {mod_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_logo_path(root: Path) -> Path | None:
    gossip_dir = root / "gossip_post"
    for name in ("logo.png", "logo.webp", "logo.jpg", "logo.jpeg"):
        candidate = gossip_dir / name
        if candidate.exists():
            return candidate
    return None


def _build_post(cgp, root: Path, post_dir: Path, item) -> Path:
    post_dir.mkdir(parents=True, exist_ok=True)

    image_path = _download_image_for_post(item.image_url, post_dir / "news_image")
    
    # Use the new AI script logic if available
    news_summary = ""
    if hasattr(cgp, "_summarize_news_text"):
        try:
            news_summary = cgp._summarize_news_text(item)
        except Exception:
            news_summary = ""

    all_lines = [ln.strip() for ln in (news_summary or "").splitlines() if ln.strip()]
    
    # Separa hashtags (para caption) do conteúdo do vídeo
    hashtags = " ".join([ln.lower() for ln in all_lines if ln.startswith("#")])
    ai_parts = [ln for ln in all_lines if not ln.startswith("#")]
    
    if len(ai_parts) >= 5:
        # Novo formato de 5 linhas: Hook / Fato / Reação / Impacto / CTA
        hook_raw = ai_parts[0]
        hook_words = hook_raw.split()[:10]
        hook_raw = " ".join(hook_words)
        
        # Combina Fato + Reação + Impacto no body
        headline_text = f"{ai_parts[1]} {ai_parts[2]} {ai_parts[3]}"
        
        # CTA emocional gerado pela IA
        cta_from_ai = ai_parts[4]
    elif len(ai_parts) >= 4:
        # Formato: Hook / Fato / Reação-Impacto / CTA
        hook_raw = ai_parts[0]
        hook_words = hook_raw.split()[:10]
        hook_raw = " ".join(hook_words)
        
        headline_text = f"{ai_parts[1]} {ai_parts[2]}"
        cta_from_ai = ai_parts[3]
    elif len(ai_parts) >= 3:
        # Formato anterior: Linha 1 = Hook, Linha 2 = Resumo, Linha 3 = CTA/Pergunta
        hook_raw = ai_parts[0]
        hook_words = hook_raw.split()[:10]
        hook_raw = " ".join(hook_words)
        
        resumo = ai_parts[1] if len(ai_parts) > 1 else ""
        cta_or_question = ai_parts[2] if len(ai_parts) > 2 else ""
        
        # Detecta se a linha 3 é CTA (contém "curte", "like") ou pergunta
        if re.search(r'\b(curte|like|deixa)\b', cta_or_question, re.I):
            cta_from_ai = cta_or_question
            headline_text = resumo
        else:
            cta_from_ai = ""
            headline_text = f"{resumo}. {cta_or_question}" if cta_or_question else resumo
    elif len(ai_parts) >= 2:
        # Fallback: se não tiver CTA, usa apenas Hook + Resumo
        hook_raw = ai_parts[0]
        hook_words = hook_raw.split()[:10]
        hook_raw = " ".join(hook_words)
        headline_text = ai_parts[1]
        cta_from_ai = ""
    else:
        if hasattr(cgp, "_build_text_layers"):
            hook_raw, gen_summary = cgp._build_text_layers(item.title, item.source)
        else:
            hook_raw = cgp._headline_for_overlay(item.title, max_chars=18, max_lines=2)
            gen_summary = cgp._headline_for_overlay(item.title, max_chars=20, max_lines=4)
        
        # Força máximo de 10 palavras no hook
        hook_words = hook_raw.split()[:10]
        hook_raw = " ".join(hook_words)
        headline_text = gen_summary
        cta_from_ai = ""

    # Normaliza pontuação que costuma virar "caixinha" (como o símbolo de reticências único)
    hook_raw = hook_raw.replace('…', '...')
    headline_text = headline_text.replace('…', '...')
    cta_from_ai = (cta_from_ai or "").replace('…', '...')

    # Remove TODAS as hashtags e caracteres especiais (para o vídeo)
    # Mantém pontuação essencial para o novo estilo narrativo (.. e ...)
    hook = re.sub(r'#\w+', '', hook_raw).strip()
    hook = re.sub(r'[^\w\s\u00C0-\u00FF!?.]', '', hook)  # Adicionado . ! e ?
    hook = re.sub(r'\s+', ' ', hook).strip()
    if hasattr(cgp, "_is_portuguese_context") and cgp._is_portuguese_context(item.source, item.title):
        if hasattr(cgp, "_normalize_pt_hook"):
            hook = cgp._normalize_pt_hook(hook, item.title)
        if hasattr(cgp, "_specialize_pt_hook"):
            hook = cgp._specialize_pt_hook(hook, item.title)
    
    headline_text = re.sub(r'#\w+', '', headline_text).strip()
    headline_text = re.sub(r'[^\w\s\u00C0-\u00FF.,!?]', '', headline_text)  # Mantém pontuação básica
    # IMPORTANTE: Não removemos múltiplos pontos aqui para preservar .. e ...
    headline_text = re.sub(r'\s+', ' ', headline_text).strip()
    if hasattr(cgp, "_fix_web_fragment"):
        headline_text = cgp._fix_web_fragment(headline_text)
    if hasattr(cgp, "_ensure_headline_completeness"):
        headline_text = cgp._ensure_headline_completeness(headline_text, item)
    if hasattr(cgp, "_rewrite_overlay_body_if_needed"):
        headline_text = cgp._rewrite_overlay_body_if_needed(headline_text, item=item)
    if hasattr(cgp, "_truncate_at_sentence_boundary"):
        headline_text = cgp._truncate_at_sentence_boundary(headline_text, max_chars=320)
    if headline_text and not re.search(r"[.!?]$", headline_text):
        headline_text += "."
    
    # Limita a 21 palavras (15 do resumo + 6 do CTA = ideal para o formato completo)
    words = headline_text.split()
    if len(words) > 21:
        headline_text = " ".join(words[:21]) + "..."

    # Força caixa alta no corpo/headline
    headline_text = headline_text.upper()

    sanitize = getattr(cgp, "_sanitize_overlay_text", _clean_text)

    hook_file = post_dir / "hook.txt"
    hook_file.write_text(sanitize(hook) + "\n", encoding="utf-8")

    summary_file = post_dir / "summary.txt"
    summary_file.write_text(sanitize(headline_text) + "\n", encoding="utf-8")

    if hasattr(cgp, "_build_display_headline"):
        headline = cgp._build_display_headline(headline_text)
    else:
        headline = cgp._headline_for_overlay(headline_text, max_chars=24, max_lines=4)
    headline_file = post_dir / "headline.txt"
    headline_file.write_text(sanitize(headline) + "\n", encoding="utf-8")

    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": item.source,
        "feed_url": item.feed_url,
        "title": _clean_text(item.title),
        "article_url": item.link,
        "published": item.published,
        "image_url": item.image_url,
        "local_image": str(image_path.relative_to(root)),
    }
    (post_dir / "news.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Caption com hashtags (para redes sociais) - hook e headline já estão sem hashtags inline
    caption_text = f"{hook}\n\n{headline_text}\n\n"
    if hashtags:
        caption_text += f"{hashtags}\n\n"
    caption_text += f"Fonte: {item.source.upper()}\nLink: {item.link}\n"
    
    (post_dir / "caption.txt").write_text(caption_text, encoding="utf-8")

    slug = cgp._make_slug(item.title)
    out_video = post_dir / "output" / f"gossip_{slug}.mp4"
    logo_path = _resolve_logo_path(root)

    # CTA contextual: usa o gerado pela IA, ou fallback com variação temática
    is_pt = cgp._is_portuguese_context(item.source, item.title)
    cta_clean = re.sub(r'#\w+', '', cta_from_ai).strip() if cta_from_ai else ""
    cta_clean = re.sub(r'[^\w\s\u00C0-\u00FF?!.,]', '', cta_clean).strip().upper() # Adicionado . , ! e ?
    
    # Se o CTA da IA for válido (5-45 chars), usa ele; senão, gera CTA temático
    if not cta_clean or len(cta_clean) < 5 or len(cta_clean) > 45:
        # Usa a função _get_random_cta do módulo base com tema
        cta_clean = cgp._get_random_cta(item.title, headline=headline_text)
        
    cta_text = cta_clean
    cgp._render_short(
        image_path,
        headline_file,
        item.source,
        out_video,
        hook_file=hook_file,
        summary_file=summary_file, # Use summary_file which contains the headline_text
        cta_text=cta_text,
        logo_path=logo_path,
    )

    # Envio para o Telegram (chamando a função implementada no create_gossip_post)
    if hasattr(cgp, "_send_video_to_telegram"):
        telegram_caption = (
            f"🔥 *Novo Gossip Post (BR)*\n\n"
            f"📍 *Fonte:* {item.source.upper()}\n"
            f"📰 *Título:* {item.title}\n"
            f"🔗 [Link da Matéria]({item.link})"
        )
        cgp._send_video_to_telegram(out_video, telegram_caption)
        
    if hasattr(cgp, "_send_text_to_telegram"):
        cgp._send_text_to_telegram(headline)

    return out_video


def _image_is_usable(url: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GossipPostBotBR/1.0)"}
    try:
        h = requests.head(url, headers=headers, timeout=20, allow_redirects=True)
        cl = int(h.headers.get("content-length") or 0)
        if cl >= 10 * 1024:
            return True
    except Exception:
        pass

    try:
        with requests.get(url, headers=headers, timeout=30, stream=True) as r:
            r.raise_for_status()
            size = 0
            for chunk in r.iter_content(chunk_size=1024 * 32):
                if not chunk:
                    continue
                size += len(chunk)
                if size >= 10 * 1024:
                    return True
            return False
    except Exception:
        return False


def _upgrade_image_url(url: str) -> str:
    # WordPress-style thumbnail: image-406x228.jpg -> image.jpg
    return re.sub(r"-\\d{2,4}x\\d{2,4}(?=\\.(jpg|jpeg|png|webp)(\\?|$))", "", url, flags=re.I)


def _guess_ext(url: str, content_type: str) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return ext
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    return ".jpg"


def _download_image_for_post(url: str, out_base: Path) -> Path:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GossipPostBotBR/1.0)"}
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
                out_path = out_base.with_suffix(_guess_ext(candidate, r.headers.get("content-type", "")))
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
        raise RuntimeError(f"Failed to download image: {last_error}") from last_error
    raise RuntimeError("Failed to download image from all candidates.")


def _fetch_from_feed(cgp, source: str, feed_url: str, skip_count: int = 0):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    resp = requests.get(feed_url, headers=headers, timeout=30)
    resp.raise_for_status()

    body = resp.text or ""
    ctype = (resp.headers.get("content-type") or "").lower()

    if "json" in ctype or body.lstrip().startswith("["):
        posts = resp.json()
        if not isinstance(posts, list):
            raise RuntimeError(f"Invalid JSON feed format for source: {source}")
        
        # Modified to handle skip_count to find next item
        valid_items = []
        for post in posts:
            if not isinstance(post, dict):
                continue
            title = _clean_text(cgp._strip_html((post.get("title") or {}).get("rendered") or ""))
            link = _clean_text(post.get("link") or "")
            published = _clean_text(post.get("date") or "")
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
                    image_url = cgp._extract_first_img_from_html(article_resp.text) or ""
                except Exception:
                    image_url = ""

            if image_url and _image_is_usable(_upgrade_image_url(image_url)):
                valid_items.append(cgp.NewsItem(
                    source=source,
                    feed_url=feed_url,
                    title=title,
                    link=link,
                    published=published,
                    image_url=_upgrade_image_url(image_url),
                    description=_clean_text(cgp._strip_html((post.get("excerpt") or {}).get("rendered") or "")),
                ))
        
        if len(valid_items) > skip_count:
            return valid_items[skip_count]
        raise RuntimeError(f"No more items for JSON source (skip={skip_count}): {feed_url}")

    root = ET.fromstring(body)
    items = root.findall("./channel/item")

    valid_items = []
    for item in items:
        title = _clean_text(item.findtext("title") or "")
        link = _clean_text(item.findtext("link") or "")
        published = _clean_text(item.findtext("pubDate") or "")
        if not title or not link:
            continue

        image_url = cgp._image_from_item(item)
        if not image_url:
            try:
                article_resp = requests.get(link, headers=headers, timeout=30)
                article_resp.raise_for_status()
                image_url = cgp._extract_first_img_from_html(article_resp.text)
            except Exception:
                image_url = None

        if image_url and _image_is_usable(_upgrade_image_url(image_url)):
            valid_items.append(cgp.NewsItem(
                source=source,
                feed_url=feed_url,
                title=title,
                link=link,
                published=published,
                image_url=_upgrade_image_url(image_url),
                description=_clean_text(item.findtext("description") or ""),
            ))

    if len(valid_items) > skip_count:
        return valid_items[skip_count]
    raise RuntimeError(f"No more items for feed (skip={skip_count}): {feed_url}")


def _make_slug(text: str, max_words: int = 5) -> str:
    """Cria um slug amigável para nome de pasta a partir do título."""
    import unicodedata
    # Normaliza para remover acentos
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    # Remove caracteres que não sejam letras, números ou espaços
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text).lower()
    words = text.split()[:max_words]
    return "-".join(words)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, help="Specific source to fetch from (e.g. ofuxico)")
    parser.add_argument("--count", type=int, default=1, help="Number of posts to generate")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    cgp = _load_base_module(root)

    out_root = root / "gossip_posts_br"
    out_root.mkdir(parents=True, exist_ok=True)

    used_links: set[str] = set()
    created = []
    
    max_tests = args.count
    count = 0
    
    target_feeds = BR_GOSSIP_FEEDS
    if args.source:
        target_feeds = [f for f in BR_GOSSIP_FEEDS if f[0].lower() == args.source.lower()]
        if not target_feeds:
            print(f"Erro: Fonte '{args.source}' não encontrada.")
            return

    today_str = datetime.now().strftime("%Y%m%d")

    # Try multiple items per feed if needed to get to unique posts
    errors = []
    skip = 0
    max_attempts = max_tests * 3  # Try up to 3x the desired count to account for duplicates/errors
    attempts = 0
    
    while count < max_tests and attempts < max_attempts:
        for source, feed_url in target_feeds:
            if count >= max_tests:
                print(f"\n✅ Meta atingida: {count}/{max_tests} posts criados!")
                break
                
            attempts += 1
            try:
                print(f"🔍 [{count+1}/{max_tests}] Buscando de {source} (tentativa {attempts}/{max_attempts})...")
                item = _fetch_from_feed(cgp, source, feed_url, skip_count=skip)
                
                if item.link in used_links:
                    print(f"  ⏭️  Notícia já usada, pulando...")
                    continue
                    
                used_links.add(item.link)
                print(f"  ✓ Nova notícia: {item.title[:60]}...")

                slug = _make_slug(item.title)
                folder_name = f"post_{today_str}_{item.source}_{slug}"
                post_dir = out_root / folder_name
                
                # Skip if folder already exists (post already created)
                if post_dir.exists():
                    print(f"  ⏭️  Pasta já existe, pulando...")
                    continue
                
                print(f"  🎬 Gerando vídeo...")
                video = _build_post(cgp, root, post_dir, item)
                count += 1
                created.append((post_dir, item.source, _clean_text(item.title), video))
                print(f"  ✅ [{count}/{max_tests}] Vídeo criado!")
                
            except Exception as e:
                error_msg = f"{source}: {type(e).__name__}: {str(e)}"
                errors.append(error_msg)
                print(f"  ❌ Erro: {error_msg}")
                continue
        
        # Increment skip for next round of feeds
        if count < max_tests:
            skip += 1

    if not created:
        print("\n" + "=" * 64)
        print("❌ NENHUM POST FOI CRIADO")
        print("=" * 64)
        print("\nErros encontrados:")
        for err in errors:
            print(f"  • {err}")
        print("=" * 64)
        raise RuntimeError("No BR gossip posts were created.")

    print("=" * 64)
    print(f"Posts criados: {len(created)}")
    for post_dir, source, title, video in created:
        print(f"- {post_dir}")
        print(f"  fonte: {source}")
        print(f"  titulo: {title}")
        print(f"  video: {video}")
    print("=" * 64)


if __name__ == "__main__":
    main()
