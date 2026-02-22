#!/usr/bin/env python3
import time
import json
import subprocess
import sys
import argparse
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

# Adiciona o diretório raiz ao path para permitir importações
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Importa as configurações e funções do script original
try:
    from scripts.create_gossip_post import (
        _fetch_first_news, 
        FEED_PROFILES, 
        create_post_for_item, 
        NewsItem, 
        _clean_text, 
        _strip_html, 
        _image_from_item,
        _extract_article_text,
    )
except ImportError:
    print("❌ Erro: Não foi possível importar scripts.create_gossip_post. Certifique-se de que o caminho está correto.")
    sys.exit(1)

HISTORY_FILE = ROOT_DIR / "gossip_post" / "history.json"
HOT_KEYWORDS = {
    "bbb": 3.0,
    "paredao": 2.5,
    "eliminacao": 2.4,
    "treta": 3.0,
    "briga": 2.2,
    "polemica": 2.2,
    "vazou": 1.8,
    "flagra": 1.8,
    "romance": 1.8,
    "beijo": 1.6,
    "separ": 1.8,
    "gravidez": 1.6,
    "carnaval": 1.4,
}

def load_history():
    """Carrega a lista de links já processados."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                content = json.load(f)
                return content if isinstance(content, list) else []
        except Exception:
            return []
    return []

def save_history(history):
    """Salva a lista de links processados, mantendo apenas os últimos 50."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-50:], f, ensure_ascii=False, indent=2)


def _parse_published(raw: str) -> datetime | None:
    t = _clean_text(raw)
    if not t:
        return None
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return dt
    except Exception:
        pass
    try:
        return parsedate_to_datetime(t)
    except Exception:
        return None


def _score_item(item: NewsItem) -> float:
    title = _clean_text(item.title).lower()
    description = _clean_text(item.description).lower()
    score = 0.0

    for key, weight in HOT_KEYWORDS.items():
        if key in title:
            score += weight

    words = title.split()
    if 7 <= len(words) <= 18:
        score += 1.4
    elif len(words) < 5:
        score -= 1.0

    if len(description) >= 120:
        score += 0.8
    elif len(description) < 60:
        score -= 0.6

    published = _parse_published(item.published)
    if published:
        try:
            age_h = (datetime.now(published.tzinfo) - published).total_seconds() / 3600.0
            if age_h <= 12:
                score += 2.6
            elif age_h <= 36:
                score += 1.8
            elif age_h <= 72:
                score += 0.8
        except Exception:
            pass

    return score

def fetch_all_upcoming_news(profile="br"):
    """Busca todas as notícias disponíveis nos feeds do perfil.

    Importante: para evitar 'corpo' truncado/incompleto no pipeline do scheduler,
    prioriza a extração do texto do artigo (quando possível) em vez do excerpt do feed.
    """
    feeds = FEED_PROFILES[profile]
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GossipPostBot/1.0)"}
    all_items = []

    for source_name, feed_url in feeds:
        try:
            resp = requests.get(feed_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                continue

            body = resp.text or ""
            ctype = (resp.headers.get("content-type") or "").lower()

            if "json" in ctype or body.lstrip().startswith("["):
                posts = resp.json()
                if isinstance(posts, list):
                    for post in posts[:10]:
                        title = _strip_html((post.get("title") or {}).get("rendered") or "")
                        link = post.get("link") or ""

                        image_url = ""
                        embedded = post.get("_embedded") or {}
                        media = embedded.get("wp:featuredmedia") or []
                        if media and isinstance(media[0], dict):
                            image_url = _clean_text(media[0].get("source_url") or "")

                        if not image_url and link:
                            try:
                                article_resp = requests.get(link, headers=headers, timeout=20)
                                if article_resp.status_code == 200:
                                    import re

                                    # Padrões simplificados para extração rápida no scheduler
                                    patterns = [
                                        r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)",
                                        r"<img[^>]+src=[\"']([^\"']+)"
                                    ]
                                    for pattern in patterns:
                                        match = re.search(pattern, article_resp.text, re.IGNORECASE)
                                        if match:
                                            url = match.group(1).strip()
                                            if url.startswith("http"):
                                                image_url = url
                                                break
                            except Exception:
                                pass

                        if title and link and image_url.startswith("http"):
                            # Evita excerpt truncado: tenta puxar texto do artigo para servir de contexto.
                            article_text = ""
                            try:
                                article_text = _extract_article_text(link)
                            except Exception:
                                article_text = ""

                            description = article_text or _strip_html((post.get("excerpt") or {}).get("rendered") or "")

                            all_items.append(
                                NewsItem(
                                    source=source_name,
                                    feed_url=feed_url,
                                    title=title,
                                    link=link,
                                    published=post.get("date") or "",
                                    image_url=image_url,
                                    description=description,
                                )
                            )
            else:
                root = ET.fromstring(body)
                for item in root.findall("./channel/item")[:10]:
                    title = _clean_text(item.findtext("title"))
                    link = _clean_text(item.findtext("link"))

                    image_url = _image_from_item(item)
                    if not image_url and link:
                        try:
                            article_resp = requests.get(link, headers=headers, timeout=20)
                            if article_resp.status_code == 200:
                                import re

                                patterns = [
                                    r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)",
                                    r"<img[^>]+src=[\"']([^\"']+)"
                                ]
                                for pattern in patterns:
                                    match = re.search(pattern, article_resp.text, re.IGNORECASE)
                                    if match:
                                        url = match.group(1).strip()
                                        if url.startswith("http"):
                                            image_url = url
                                            break
                        except Exception:
                            pass

                    if title and link and image_url and image_url.startswith("http"):
                        # Evita description truncado do RSS: tenta puxar artigo.
                        article_text = ""
                        try:
                            article_text = _extract_article_text(link)
                        except Exception:
                            article_text = ""

                        description = article_text or _strip_html(item.findtext("description") or "")

                        all_items.append(
                            NewsItem(
                                source=source_name,
                                feed_url=feed_url,
                                title=title,
                                link=link,
                                published=_clean_text(item.findtext("pubDate")),
                                image_url=image_url,
                                description=description,
                            )
                        )
        except Exception:
            continue
    return all_items

def run_scheduler():
    print("🚀 Agendador de Fofocas (MODO TRIPLE) Iniciado!")
    print("⏰ Horários fixos: 12:00, 18:00 e 21:00.")
    print("📦 Lote: 3 posts por execução.")
    print(f"📁 Histórico em: {HISTORY_FILE}")
    print("-" * 40)

    # Prepara argumentos simulados para o renderer
    args = argparse.Namespace(profile="br", logo="")

    # Evita rodar várias vezes no mesmo horário
    last_processed_hour: int | None = None

    target_hours = {12, 18, 21}

    while True:
        try:
            now = datetime.now()

            if now.hour in target_hours and last_processed_hour != now.hour:
                history = load_history()

                print(f"\n[{now.strftime('%H:%M:%S')}] 🔔 Horário atingido! Verificando feeds...")

                # Busca todas as notícias dos feeds BR
                all_items = fetch_all_upcoming_news("br")

                # Filtra o que já foi postado
                new_items = [it for it in all_items if it.link not in history]
                new_items.sort(key=_score_item, reverse=True)

                if not new_items:
                    print("😴 Nenhuma notícia nova encontrada.")
                else:
                    # Pega as 3 primeiras novidades
                    to_process = new_items[:3]
                    print(f"✨ Encontradas {len(new_items)} novidades. Processando as {len(to_process)} primeiras...")

                    for i, item in enumerate(to_process, 1):
                        print(f"\n[{i}/{len(to_process)}] 🎬 Iniciando: {item.title[:60]}...")

                        success = create_post_for_item(item, args)

                        if success:
                            history.append(item.link)
                            save_history(history)
                            print(f"✅ Item {i} finalizado com sucesso.")
                        else:
                            print(f"⚠️ Erro ao processar item {i}.")

                last_processed_hour = now.hour
                print(f"\n💤 Lote das {now.hour:02d}h concluído. Aguardando próximo horário...")

        except Exception as e:
            print(f"⚠️ Erro inesperado no agendador: {e}")

        # Checa com frequência para bater certinho o horário
        time.sleep(30)

if __name__ == "__main__":
    try:
        run_scheduler()
    except KeyboardInterrupt:
        print("\n👋 Agendador parado pelo usuário.")
        sys.exit(0)
