#!/usr/bin/env python3
"""
Processador unificado de requisições da fila do Telegram.

Este módulo concentra toda a lógica de processamento da fila para evitar
divergência entre versões antigas dos scripts.
"""

import json
import os
import re
import subprocess
import sys
import unicodedata
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.ai_client import OpenAIConfig, is_openai_configured
from scripts.create_gossip_post import NewsItem, build_editorial_pack_for_item

QUEUE_DIR = ROOT_DIR / "telegram_queue"
QUEUE_DIR.mkdir(exist_ok=True)

# Configurações do Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def send_message(chat_id: str, text: str) -> bool:
    """Envia mensagem para o Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN não configurado; aviso não enviado.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        response = requests.post(url, json=data, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")
        return False


def _extract_video_metadata(video_url: str) -> tuple[str, str]:
    """Extrai título e descrição via yt-dlp sem baixar o arquivo."""
    def _run_metadata(extractor_api: str | None = None) -> subprocess.CompletedProcess:
        cmd = [
            "yt-dlp",
            "--print",
            "%(title)s",
            "--print",
            "%(description)s",
            "--skip-download",
            "--no-warnings",
        ]
        if extractor_api:
            cmd.extend(["--extractor-args", f"twitter:api={extractor_api}"])
        cmd.append(video_url)
        return subprocess.run(
            cmd,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )

    try:
        result = _run_metadata()
        err_text = ((result.stderr or "").strip() or (result.stdout or "").strip())
        if result.returncode != 0 and "Error(s) while querying API" in err_text:
            result = _run_metadata("syndication")
        if result.returncode == 0:
            lines = (result.stdout or "").splitlines()
            if lines:
                title = lines[0].strip()
                description = "\n".join(lines[1:]).strip()
                return title, description
    except Exception as e:
        print(f"⚠️ Não foi possível extrair metadados do vídeo: {e}")
    return "Flagra no X", ""


def _normalize_video_text(raw: str) -> str:
    clean = (raw or "").split("|")[0]
    clean = re.sub(r"\(@[^)]+\)", "", clean)
    clean = re.sub(r"\bon\s+x\b", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"https?://\S+", "", clean)
    clean = clean.replace("—", "-").replace("–", "-")

    if " - " in clean:
        _, right = clean.split(" - ", 1)
        if len(right.split()) >= 4:
            clean = right

    allowed_punct = set(".,!?-:;'\"()")
    filtered_chars: list[str] = []
    for ch in clean:
        cat = unicodedata.category(ch)
        if ch in allowed_punct or cat.startswith(("L", "N")) or ch.isspace():
            filtered_chars.append(ch)
    clean = "".join(filtered_chars)

    return re.sub(r"\s+", " ", clean).strip(" -|")


def _detect_video_theme(text: str) -> str:
    lowered = (text or "").lower()
    if any(k in lowered for k in ("bbb", "paredao", "elimin", "lider", "prova")):
        return "bbb"
    if any(k in lowered for k in ("treta", "briga", "discuss", "barraco", "clim", "grit")):
        return "treta"
    if any(k in lowered for k in ("beijo", "beij", "casal", "romance", "ship", "ficou")):
        return "romance"
    if any(k in lowered for k in ("trai", "chifre", "termin", "separ", "ex ", "ex-")):
        return "separacao"
    if any(k in lowered for k in ("flagra", "vazou", "video", "imagens", "registro")):
        return "flagra"
    return "generic"


def _trim_words(text: str, limit: int) -> str:
    words = [w for w in (text or "").split() if w]
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]).rstrip(" ,.;:-") + "..."


def _safe_upper(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().upper()


def _split_sentences(text: str) -> list[str]:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return []
    parts = re.split(r"(?<=[.!?])\s+", t)
    out = []
    for p in parts:
        s = p.strip(" .")
        if len(s.split()) >= 4:
            out.append(s)
    return out


def _normalize_editorial_hook(text: str) -> str:
    words = [w for w in _clean_telegram_text(text, 90).split() if w]
    if not words:
        return "QUE BABADO?"
    words = words[:5]
    if len(words) < 3:
        words = (words + ["WEB", "DESCONFIA"])[:3]
    out = " ".join(words)
    if not out.endswith(("?", "!")):
        out += "?"
    return _safe_upper(out)


def _normalize_editorial_headline(text: str, fallback: str = "") -> str:
    base = _clean_telegram_text(text, 80) or _clean_telegram_text(fallback, 80)
    words = [w for w in base.split() if w]
    if not words:
        return "Web dividida"
    return " ".join(words[:4])


def _pick_editorial_body(theme: str, seed_text: str) -> str:
    body_by_theme = {
        "bbb": ["Jogo virou", "Web dividida", "Virada inesperada"],
        "treta": ["Clima tenso", "Treta explosiva", "Detalhe polemico"],
        "romance": ["Clima estranho", "Web desconfia", "Flagra decisivo"],
        "separacao": ["Crise exposta", "Detalhe sensivel", "Web reage forte"],
        "flagra": ["Detalhe polemico", "Caso repercute", "Virada inesperada"],
        "generic": ["Revelacao chocante", "Detalhe polemico", "Web dividida"],
    }
    options = body_by_theme.get(theme, body_by_theme["generic"])
    digest = hashlib.md5((seed_text or "body").encode("utf-8")).hexdigest()
    idx = int(digest, 16) % len(options)
    return options[idx]


def _build_editorial_description(raw_desc: str, title: str, fallback_desc: str) -> tuple[str, str]:
    merged = _clean_telegram_text(raw_desc, 700)
    base_lines = _split_sentences(merged) + _split_sentences(_clean_telegram_text(fallback_desc, 700))

    if len(base_lines) >= 2:
        line_1 = _trim_words(base_lines[0], 15).rstrip(".!?") + "."
        line_2 = _trim_words(base_lines[1], 15).rstrip(".!?") + "."
        return line_1, line_2

    title_base = _clean_telegram_text(title, 180)
    title_base = re.split(r"\s*[-:|]\s*", title_base, maxsplit=1)[0].strip()
    title_base = _trim_words(title_base, 12).rstrip(".!?")
    if not title_base:
        title_base = "O caso"

    return (
        f"{title_base} chamou atencao nas redes.",
        "A web reagiu e as opinioes ficaram divididas.",
    )


def _normalize_editorial_cta(text: str, theme: str) -> str:
    t = _clean_telegram_text(text, 60)
    valid_action = bool(re.search(r"\b(comenta|curte|salva|segue|marca|manda)\b", t, flags=re.I))
    if t and "?" not in t and valid_action:
        return _safe_upper(t)

    fallback = {
        "bbb": "COMENTA QUEM VOCE APOIA!",
        "treta": "COMENTA QUEM TEM RAZAO!",
        "romance": "COMENTA SE SHIPPA!",
        "separacao": "COMENTA O QUE ACHOU!",
        "flagra": "SALVA ESSE POST!",
        "generic": "COMENTA O QUE ACHOU!",
    }
    return fallback.get(theme, fallback["generic"])


def _build_video_copy_with_ai(title: str, description: str) -> tuple[str, str, str, str, str] | None:
    cfg = OpenAIConfig()
    if not is_openai_configured(cfg):
        return None

    api_key = os.getenv(cfg.api_key_env, "").strip()
    if not api_key:
        return None

    context = _clean_telegram_text(f"{title}. {description}", 1600)
    if not context:
        return None

    payload = {
        "model": os.getenv("GOSSIP_SUMMARY_MODEL", cfg.model).strip() or cfg.model,
        "temperature": 0.7,
        "max_completion_tokens": 220,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Voce cria textos no formato editorial Babado Rapido (PT-BR).\n"
                    "Retorne exatamente 5 linhas, sem hashtags e sem emojis:\n"
                    "1) HOOK: pergunta/reacao com 3 a 5 palavras.\n"
                    "2) HEADLINE: ate 4 palavras (personagem + acao curta).\n"
                    "3) BODY: expressao editorial forte de 2 a 3 palavras.\n"
                    "4) DESCRICAO: exatamente 2 frases curtas interpretativas.\n"
                    "5) CTA: chamada curta de engajamento (imperativa).\n"
                    "Tom: reacao da web, nao manchete literal de portal."
                ),
            },
            {
                "role": "user",
                "content": f"Base do video:\n{context}",
            },
        ],
    }

    try:
        r = requests.post(
            f"{cfg.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
        if not content:
            return None
        lines = []
        for raw in str(content).splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            line = re.sub(
                r"^(gancho|hook|headline|titulo|title|body|corpo|tarja|descricao|descrição|description|cta|linha|line)\s*\d*\s*[:\-–—=]\s*",
                "",
                line,
                flags=re.IGNORECASE,
            ).strip()
            if line:
                lines.append(line)

        if len(lines) >= 5:
            hook = lines[0]
            headline = lines[1]
            body = lines[2]
            desc = lines[3]
            cta = lines[4]
            return hook, headline, body, desc, cta
        if len(lines) >= 4:
            hook = lines[0]
            headline = lines[1]
            body = lines[2]
            desc = lines[3]
            return hook, headline, body, desc, "COMENTA O QUE ACHOU!"
        return None
    except Exception:
        return None


def _build_video_copy_fallback(title: str, description: str) -> tuple[str, str, str, str, str]:
    base = title or description or "Flagra que deu o que falar"
    theme = _detect_video_theme(f"{title} {description}")

    hooks = {
        "bbb": [
            "QUE JOGADA FOI ESSA?",
            "WEB DESCONFIA DISSO?",
        ],
        "treta": [
            "TRETA FORA DE CONTROLE?",
            "QUE CLIMA PESADO?!",
        ],
        "romance": [
            "CLIMA ESTRANHO NO AR?",
            "WEB SHIPPA OU NAO?",
        ],
        "separacao": [
            "CRISE OU IMPRESSAO?",
            "WEB LEVANTOU SUSPEITA?",
        ],
        "flagra": [
            "QUE BABADO NISSO?!",
            "DETALHE CHAMOU ATENCAO?",
        ],
        "generic": [
            "QUE BABADO NISSO?",
            "WEB DIVIDIU OPINIAO?",
        ],
    }

    digest = hashlib.md5(_clean_telegram_text(base, 240).encode("utf-8")).hexdigest()
    seed = int(digest, 16)
    hook_pool = hooks.get(theme, hooks["generic"])
    hook = hook_pool[seed % len(hook_pool)]

    headline = _normalize_editorial_headline(title, fallback=description)
    body = _pick_editorial_body(theme, seed_text=base)
    desc_1, desc_2 = _build_editorial_description("", title, description)
    desc = f"{desc_1} {desc_2}".strip()
    cta = _normalize_editorial_cta("", theme)
    return hook, headline, body, desc, cta


def _build_video_copy_legacy(raw_title: str, raw_description: str = "") -> tuple[str, str, str, str, str, str]:
    """Legacy generator kept as fallback if shared V5 pipeline fails."""
    clean = _normalize_video_text(raw_title)
    desc_clean = _normalize_video_text(raw_description)

    if clean.endswith("...") and desc_clean and len(desc_clean.split()) >= 6:
        clean = desc_clean
    clean = clean or "Flagra que deu o que falar"
    theme = _detect_video_theme(f"{clean} {desc_clean}")

    ai_pack = _build_video_copy_with_ai(clean, desc_clean)
    if ai_pack:
        hook_raw, headline_raw, body_raw, desc_raw, cta_raw = ai_pack
    else:
        hook_raw, headline_raw, body_raw, desc_raw, cta_raw = _build_video_copy_fallback(clean, desc_clean)

    hook = _normalize_editorial_hook(hook_raw)
    headline = _normalize_editorial_headline(headline_raw, fallback=clean)
    body = _pick_editorial_body(theme, seed_text=_clean_telegram_text(body_raw, 120) or clean)
    desc_1, desc_2 = _build_editorial_description(desc_raw, clean, desc_clean)
    cta = _normalize_editorial_cta(cta_raw, theme)

    if not hook:
        hook = "QUE BABADO?"
    if not headline:
        headline = "Web dividida"
    if not body:
        body = "Revelacao chocante"
    if not cta:
        cta = "COMENTA O QUE ACHOU!"

    telegram_title = _clean_telegram_text(raw_title, 180) or headline
    telegram_description = f"{desc_1} {desc_2}".strip()
    if len(telegram_description) > 700:
        telegram_description = telegram_description[:700].rsplit(" ", 1)[0] + "..."
    return hook, headline, body, cta, telegram_title, telegram_description


def _build_video_copy(raw_title: str, raw_description: str = "", video_url: str = "") -> tuple[str, str, str, str, str, str]:
    """Build copy for Telegram video posts using the same V5 engine as scheduler."""
    clean_title = _normalize_video_text(raw_title) or "Flagra no X"
    clean_desc = _normalize_video_text(raw_description)

    item = NewsItem(
        source="telegram_video",
        feed_url="telegram://x",
        title=clean_title,
        link=video_url.strip(),
        published="",
        image_url="",
        description=clean_desc,
    )
    hook_history_path = ROOT_DIR / "gossip_post" / "hook_history.json"

    try:
        pack = build_editorial_pack_for_item(item, hook_history_path=hook_history_path)
        hook = pack.get("hook", "").strip() or "QUE BABADO?"
        headline = pack.get("headline", "").strip() or "Web dividida"
        body = pack.get("body", "").strip() or "A web reagiu e as opinioes ficaram divididas"
        cta = pack.get("cta", "").strip() or "COMENTA O QUE ACHOU!"

        telegram_title = _clean_telegram_text(raw_title, 180) or headline
        telegram_description = _clean_telegram_text(pack.get("description", ""), 700) or headline
        return hook, headline, body, cta, telegram_title, telegram_description
    except Exception as exc:
        print(f"⚠️ Falha no motor V5 compartilhado, usando fallback legado: {exc}")
        return _build_video_copy_legacy(raw_title, raw_description)


def _clean_telegram_text(text: str, max_len: int) -> str:
    allowed_punct = set(".,!?-:;'\"()")
    filtered_chars: list[str] = []
    for ch in text or "":
        cat = unicodedata.category(ch)
        if ch in allowed_punct or cat.startswith(("L", "N")) or ch.isspace():
            filtered_chars.append(ch)
    clean = re.sub(r"\s+", " ", "".join(filtered_chars)).strip()
    if not clean:
        return ""
    if len(clean) > max_len:
        clean = clean[:max_len].rsplit(" ", 1)[0] + "..."
    return clean


def process_foto_request(request: Dict[str, Any]) -> bool:
    """Processa requisição de post com foto."""
    print(f"\n📸 Processando post com foto: {request['id']}")
    print(f"🔗 Link: {request['article_url']}")

    chat_id = request["chat_id"]
    article_url = request["article_url"]

    send_message(chat_id, f"🔄 Processando post `{request['id']}`...")

    try:
        print(f"📰 Executando create_gossip_post.py para URL: {article_url}")

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT_DIR / "scripts" / "create_gossip_post.py"),
                "--profile",
                "br",
                "--url",
                article_url,
            ],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=180,
        )

        print(f"Return code: {result.returncode}")
        print(f"STDOUT: {result.stdout[:500]}")
        if result.stderr:
            print(f"STDERR: {result.stderr[:500]}")

        if result.returncode == 0:
            send_message(chat_id, f"✅ Post `{request['id']}` criado!\n\nVídeo será enviado em breve.")
            return True
        error_msg = f"❌ Erro no processamento (código {result.returncode})"
        print(error_msg)
        send_message(chat_id, error_msg)
        return False

    except subprocess.TimeoutExpired:
        error_msg = "❌ Timeout ao processar (>3 minutos)"
        print(error_msg)
        send_message(chat_id, error_msg)
        return False
    except Exception as e:
        error_msg = f"❌ Erro ao processar: {e}"
        print(error_msg)
        send_message(chat_id, error_msg)
        return False


def process_video_request(request: Dict[str, Any]) -> bool:
    """Processa requisição de post com vídeo."""
    print(f"\n🎥 Processando post com vídeo: {request['id']}")

    chat_id = request["chat_id"]
    video_url = request["video_url"]

    send_message(chat_id, f"🔄 Gerando post de vídeo para `{request['id']}`...")

    try:
        print(f"🎬 Executando create_new_video_post.py para VÍDEO: {video_url}")
        raw_title, raw_description = _extract_video_metadata(video_url)
        hook, headline, body, cta, telegram_title, telegram_description = _build_video_copy(
            raw_title,
            raw_description,
            video_url,
        )
        duration = 11.0

        args = [
            sys.executable,
            str(ROOT_DIR / "scripts" / "create_new_video_post.py"),
            "--url",
            video_url,
            "--hook",
            hook,
            "--headline",
            headline,
            "--body",
            body,
            "--raw-editorial",
            "--cta",
            cta,
            "--duration",
            str(duration),
            "--name",
            f"telegram_{request['id']}",
            "--skip-preview",
            "--send-original",
            "--telegram-title",
            telegram_title,
            "--telegram-description",
            telegram_description,
        ]

        result = subprocess.run(
            args,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )

        print(f"Return code: {result.returncode}")
        print(f"STDOUT: {result.stdout[:800]}")

        if result.returncode == 0:
            send_message(chat_id, f"✅ Vídeo `{request['id']}` processado com sucesso!\n\nEnviando o arquivo...")
            return True
        print(f"STDERR: {result.stderr[:800]}")
        err_text = ((result.stderr or result.stdout or "").strip() or "erro desconhecido")
        err_first_line = err_text.splitlines()[0][:220]
        if "Dependency: Unspecified" in err_text:
            err_first_line = "falha temporária da API do X/Twitter (retry automático já aplicado)"
        send_message(chat_id, f"❌ Erro ao processar vídeo: {err_first_line}")
        return False

    except Exception as e:
        print(f"Erro: {e}")
        send_message(chat_id, f"❌ Erro: {e}")
        return False


def process_queue() -> int:
    """Processa todas as requisições pendentes na fila."""
    print("🔍 Verificando fila de requisições...")

    pending_files = sorted(QUEUE_DIR.glob("request_*.json"))

    if not pending_files:
        print("✅ Nenhuma requisição pendente.")
        return 0

    print(f"📦 Encontradas {len(pending_files)} requisições")

    processed = 0
    for request_file in pending_files:
        try:
            with open(request_file, "r", encoding="utf-8") as f:
                request = json.load(f)

            if request.get("status") != "pending":
                print(f"⏭️  Pulando {request_file.name} (status: {request.get('status')})")
                continue

            request["status"] = "processing"
            request["processing_started"] = datetime.now().isoformat()
            with open(request_file, "w", encoding="utf-8") as f:
                json.dump(request, f, indent=2, ensure_ascii=False)

            success = False
            if request["type"] == "foto":
                success = process_foto_request(request)
            elif request["type"] == "video":
                success = process_video_request(request)
            else:
                print(f"⚠️ Tipo de requisição desconhecido: {request.get('type')}")

            request["status"] = "completed" if success else "failed"
            request["processing_finished"] = datetime.now().isoformat()
            with open(request_file, "w", encoding="utf-8") as f:
                json.dump(request, f, indent=2, ensure_ascii=False)

            if success:
                processed += 1
        except Exception as e:
            print(f"⚠️ Erro ao processar {request_file.name}: {e}")
            continue

    print(f"\n✅ Processadas {processed} requisições com sucesso")
    return processed


def main() -> None:
    print("🚀 Iniciando processador de requisições do Telegram")
    print(f"📁 Fila em: {QUEUE_DIR}")

    processed = process_queue()
    if processed > 0:
        print(f"\n🎉 {processed} post(s) criado(s) com sucesso!")
    else:
        print("\n📭 Nenhum post foi processado.")


if __name__ == "__main__":
    main()
