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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
QUEUE_DIR = ROOT_DIR / "telegram_queue"
QUEUE_DIR.mkdir(exist_ok=True)

# Configurações do Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8519683231:AAH1RsrgaYmo3v99hd_yfktgoFWHU2AWrP0"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "1015015823"


def send_message(chat_id: str, text: str) -> bool:
    """Envia mensagem para o Telegram."""
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
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--print",
                "%(title)s",
                "--print",
                "%(description)s",
                "--skip-download",
                "--no-warnings",
                video_url,
            ],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
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


def _build_video_copy(raw_title: str, raw_description: str = "") -> tuple[str, str]:
    """Monta hook/headline curtos para render de vídeo."""
    clean = _normalize_video_text(raw_title)
    desc_clean = _normalize_video_text(raw_description)

    # Alguns títulos do X chegam truncados com reticências.
    # Se houver descrição útil, prefere o começo dela para evitar palavra cortada.
    if clean.endswith("...") and desc_clean and len(desc_clean.split()) >= 6:
        clean = desc_clean

    clean = clean or "Flagra que deu o que falar"

    lowered = clean.lower()
    if any(k in lowered for k in ("beijo", "beij", "casal", "romance", "apaixon")):
        hook = "NAO E MAIS SEGREDO!"
    elif any(k in lowered for k in ("treta", "briga", "discuss", "barraco")):
        hook = "A TRETA EXPLODIU!"
    elif any(k in lowered for k in ("bbb", "paredao", "elimin")):
        hook = "PEGOU FOGO!"
    else:
        hook = "VEJA O FLAGRANTE!"

    headline = clean.upper()
    if len(headline) > 120:
        headline = headline[:120].rsplit(" ", 1)[0]
    return hook, headline


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
        hook, headline = _build_video_copy(raw_title, raw_description)
        duration = float(request.get("duration", 15))
        telegram_title = _clean_telegram_text(raw_title, 180) or headline
        telegram_description = _clean_telegram_text(raw_description, 700) or headline

        args = [
            sys.executable,
            str(ROOT_DIR / "scripts" / "create_new_video_post.py"),
            "--url",
            video_url,
            "--hook",
            hook,
            "--headline",
            headline,
            "--duration",
            str(duration),
            "--name",
            f"telegram_{request['id']}",
            "--skip-preview",
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
        send_message(chat_id, f"❌ Erro ao processar vídeo: {result.stderr[:200]}")
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
