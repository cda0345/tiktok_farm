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


def _enforce_editorial_markers(text: str) -> str:
    out = re.sub(r"\s+", " ", (text or "").strip())
    if not out:
        out = "CONTEXTO: CASO VIROU ASSUNTO NAS REDES."
    if not re.search(r"\bCONTEXTO\s*:", out, flags=re.I):
        out = f"CONTEXTO: {out}"
    if not re.search(r"\bSEGUNDO\s+F[ÃA]S\b", out, flags=re.I):
        out = f"{out} SEGUNDO FAS, .. A WEB DIVIDIU OPINIOES."
    if not re.search(r"\bA\s+REPERCUSSAO\s+COMECOU\s+APOS\b", out, flags=re.I):
        out = f"{out} A REPERCUSSAO COMECOU APOS O TRECHO VIRALIZAR..."
    return re.sub(r"\s+", " ", out).strip()


def _strip_context_label(text: str) -> str:
    out = re.sub(r"\s+", " ", (text or "").strip())
    out = re.sub(r"(^|\.\s+)\bCONTEXTO\s*:\s*", r"\1", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip()


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


def _build_video_copy_with_ai(title: str, description: str) -> tuple[str, str, str] | None:
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
                    "Voce escreve copy viral para post vertical de fofoca (PT-BR). "
                    "Entregue exatamente 5 linhas em CAPS, sem hashtags e sem emojis: "
                    "1) HOOK FACTUAL editorial (6 a 10 palavras), "
                    "2) CONTEXTO em 1 frase iniciando obrigatoriamente com 'CONTEXTO:', "
                    "3) REACAO WEB iniciando obrigatoriamente com 'SEGUNDO FAS,' e usando suspense '..', "
                    "4) DESDOBRAMENTO iniciando obrigatoriamente com 'A REPERCUSSAO COMECOU APOS' (preferir final com '...'), "
                    "5) PERGUNTA editorial curta que forca posicionamento. "
                    "Nao invente fatos, nomes ou contexto que nao estejam no material enviado."
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
                r"^(gancho|hook|fato|reacao|reação|impacto|cta|linha|line)\s*\d*\s*[:\-–—=]\s*",
                "",
                line,
                flags=re.IGNORECASE,
            ).strip()
            if line:
                lines.append(line)

        if len(lines) >= 5:
            hook = lines[0]
            body = f"{lines[1]} {lines[2]} {lines[3]}"
            cta = lines[4]
        elif len(lines) >= 3:
            hook = lines[0]
            body = " ".join(lines[1:3])
            cta = "COMENTA O QUE ACHOU!"
        elif len(lines) >= 2:
            hook = lines[0]
            body = lines[1]
            cta = "COMENTA O QUE ACHOU!"
        else:
            return None

        return hook, body, cta
    except Exception:
        return None


def _build_video_copy_fallback(title: str, description: str) -> tuple[str, str, str]:
    base = title or description or "Flagra que deu o que falar"
    theme = _detect_video_theme(f"{title} {description}")

    hooks = {
        "bbb": [
            "DETALHE DA APURACAO DIVIDIU A WEB",
            "NO BBB, A CENA QUE PEGOU FOGO",
        ],
        "treta": [
            "A TRETA SAIU DO CONTROLE RAPIDO",
            "BASTIDOR QUENTE EXPLODIU NAS REDES",
        ],
        "romance": [
            "FLAGRA REACENDEU RUMORES DE ROMANCE",
            "O CLIMA ENTREGOU TUDO NESSE VIDEO",
        ],
        "separacao": [
            "UM DETALHE LEVANTOU RUMOR DE FIM",
            "A WEB APONTOU SINAL DE CRISE",
        ],
        "flagra": [
            "O VIDEO QUE VIROU ASSUNTO DA HORA",
            "FLAGRA RAPIDO ABRIU NOVA POLEMICA",
        ],
        "generic": [
            "O DETALHE QUE NINGUEM IGNOROU",
            "ESSA CENA ACENDEU O DEBATE",
        ],
    }
    editorial_questions = {
        "bbb": "ISSO FOI ESTRATEGIA OU EXAGERO?",
        "treta": "ISSO E CRITICA JUSTA OU OPORTUNISMO?",
        "romance": "ISSO FOI NATURAL OU JOGADA PRA ENGAJAR?",
        "separacao": "ISSO INDICA CRISE REAL OU LEITURA FORCADA?",
        "flagra": "ISSO MUDA A LEITURA DO CASO OU NAO?",
        "generic": "ISSO E ANALISE JUSTA OU EXAGERO?",
    }

    digest = hashlib.md5(_clean_telegram_text(base, 240).encode("utf-8")).hexdigest()
    seed = int(digest, 16)
    hook_pool = hooks.get(theme, hooks["generic"])
    hook = hook_pool[seed % len(hook_pool)]

    source_lines = _split_sentences(description) + _split_sentences(title)
    fact = source_lines[0] if source_lines else base
    fact = _trim_words(fact, 14).rstrip(".")

    reaction_by_theme = {
        "bbb": ".. A TORCIDA DIVIDIU LEITURAS SOBRE O MOVIMENTO",
        "treta": ".. A WEB CRITICOU E DEFENDEU AO MESMO TEMPO",
        "romance": ".. FAS APONTARAM CLIMA E DEBATERAM O FLAGRA",
        "separacao": ".. PARTE DA WEB LEU COMO SINAL DE CRISE",
        "flagra": ".. A WEB LEVANTOU CRITICAS E DEFESAS RAPIDAS",
        "generic": ".. O ASSUNTO DIVIDIU OPINIOES NAS REDES",
    }
    impact_by_theme = {
        "bbb": "A REPERCUSSAO COMECOU APOS RECORTES VIRALIZAREM...",
        "treta": "A REPERCUSSAO COMECOU APOS O TRECHO RODAR NAS PAGINAS...",
        "romance": "A REPERCUSSAO COMECOU APOS O FLAGRA TOMAR AS REDES...",
        "separacao": "A REPERCUSSAO COMECOU APOS LEITURAS DE BASTIDOR...",
        "flagra": "A REPERCUSSAO COMECOU APOS O VIDEO SUBIR NAS CONTAS...",
        "generic": "A REPERCUSSAO COMECOU APOS A CENA VIRAR DEBATE...",
    }

    body = (
        f"CONTEXTO: {fact}. "
        f"SEGUNDO FAS, {reaction_by_theme[theme]} "
        f"{impact_by_theme[theme]}"
    )
    body = _trim_words(body, 44)
    cta = editorial_questions.get(theme, editorial_questions["generic"])
    return hook, body, cta


def _build_video_copy(raw_title: str, raw_description: str = "") -> tuple[str, str, str, str, str]:
    """Monta hook/headline/cta editoriais para render de vídeo."""
    clean = _normalize_video_text(raw_title)
    desc_clean = _normalize_video_text(raw_description)

    if clean.endswith("...") and desc_clean and len(desc_clean.split()) >= 6:
        clean = desc_clean
    clean = clean or "Flagra que deu o que falar"

    ai_pack = _build_video_copy_with_ai(clean, desc_clean)
    if ai_pack:
        hook_raw, headline_raw, cta_raw = ai_pack
    else:
        hook_raw, headline_raw, cta_raw = _build_video_copy_fallback(clean, desc_clean)

    hook = _safe_upper(_clean_telegram_text(hook_raw, 90))
    headline_enforced = _enforce_editorial_markers(headline_raw)
    headline_enforced = _strip_context_label(headline_enforced)
    headline = _safe_upper(_clean_telegram_text(headline_enforced, 260))
    cta = _safe_upper(_clean_telegram_text(cta_raw, 52))

    if not hook:
        hook = "O DETALHE QUE NINGUEM IGNOROU"
    if not headline:
        headline = _safe_upper(clean)
    if not cta:
        cta = "COMENTA O QUE ACHOU!"

    telegram_title = _clean_telegram_text(raw_title, 180) or headline
    base_desc = _clean_telegram_text(raw_description, 700) or _clean_telegram_text(headline, 700)
    telegram_description = f"{hook}. {base_desc}".strip()
    if len(telegram_description) > 700:
        telegram_description = telegram_description[:700].rsplit(" ", 1)[0] + "..."
    return hook, headline, cta, telegram_title, telegram_description


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
        hook, headline, cta, telegram_title, telegram_description = _build_video_copy(raw_title, raw_description)
        duration = float(request.get("duration", 20))

        args = [
            sys.executable,
            str(ROOT_DIR / "scripts" / "create_new_video_post.py"),
            "--url",
            video_url,
            "--hook",
            hook,
            "--headline",
            headline,
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
