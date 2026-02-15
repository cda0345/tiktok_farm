#!/usr/bin/env python3
"""
Webhook handler para o bot do Telegram.
Alternativa ao polling - recebe atualizações via HTTP.

Para usar com GitHub Actions, você pode configurar um webhook
que dispara o workflow automaticamente quando uma mensagem chega.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
QUEUE_DIR = ROOT_DIR / "telegram_queue"
QUEUE_DIR.mkdir(exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8519683231:AAH1RsrgaYmo3v99hd_yfktgoFWHU2AWrP0"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "1015015823"


def set_webhook(webhook_url: str) -> bool:
    """
    Configura o webhook do Telegram.
    
    Args:
        webhook_url: URL que receberá as atualizações (ex: https://seu-dominio.com/webhook)
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    data = {"url": webhook_url}
    
    try:
        response = requests.post(url, json=data, timeout=30)
        if response.status_code == 200:
            print(f"✅ Webhook configurado: {webhook_url}")
            return True
        else:
            print(f"❌ Erro ao configurar webhook: {response.text}")
            return False
    except Exception as e:
        print(f"⚠️ Erro: {e}")
        return False


def delete_webhook() -> bool:
    """Remove o webhook (volta ao polling mode)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
    
    try:
        response = requests.post(url, timeout=30)
        if response.status_code == 200:
            print("✅ Webhook removido")
            return True
        else:
            print(f"❌ Erro: {response.text}")
            return False
    except Exception as e:
        print(f"⚠️ Erro: {e}")
        return False


def get_webhook_info() -> Dict[str, Any]:
    """Retorna informações sobre o webhook atual."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.json().get("result", {})
        return {}
    except Exception:
        return {}


def handle_webhook_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processa uma atualização recebida via webhook.
    
    Args:
        update: Dados do update do Telegram
    
    Returns:
        Response para o Telegram (200 OK)
    """
    if "message" not in update:
        return {"status": "ok", "message": "No message in update"}
    
    message = update["message"]
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "").strip()
    
    # Verifica se é do chat autorizado
    if chat_id != TELEGRAM_CHAT_ID:
        return {"status": "ignored", "message": "Unauthorized chat"}
    
    # Processa comando
    if text.startswith("/"):
        result = process_command(chat_id, text)
        return {"status": "ok", "result": result}
    
    # Detecção automática de links do X/Twitter (Gossip simplificado)
    if "x.com" in text or "twitter.com" in text:
        result = handle_post_video(chat_id, text)
        return {"status": "ok", "result": result}
    
    return {"status": "ok", "message": "Not a command"}


def process_command(chat_id: str, text: str) -> str:
    """Processa comandos do bot."""
    parts = text.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if command == "/post_foto":
        return handle_post_foto(chat_id, args)
    
    elif command == "/post_video":
        return handle_post_video(chat_id, args)
    
    elif command == "/status":
        return handle_status(chat_id)
    
    return "unknown_command"


def send_message(chat_id: str, text: str) -> bool:
    """Envia mensagem para o Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    
    try:
        response = requests.post(url, json=data, timeout=30)
        return response.status_code == 200
    except Exception:
        return False


def handle_post_foto(chat_id: str, args: str) -> str:
    """Cria requisição de post com foto."""
    if not args or not args.startswith("http"):
        send_message(
            chat_id,
            "❌ Por favor, forneça o link da matéria.\n\n"
            "Exemplo: `/post_foto https://contigo.com.br/noticias/sua-materia`"
        )
        return "invalid_args"
    
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    request = {
        "id": request_id,
        "type": "foto",
        "article_url": args.strip(),
        "created_at": datetime.now().isoformat(),
        "chat_id": chat_id,
        "status": "pending"
    }
    
    request_file = QUEUE_DIR / f"request_{request_id}.json"
    with open(request_file, "w", encoding="utf-8") as f:
        json.dump(request, f, indent=2, ensure_ascii=False)
    
    send_message(
        chat_id,
        f"✅ *Requisição criada!*\n\n"
        f"📋 ID: `{request_id}`\n"
        f"📸 Tipo: Post com foto\n"
        f"🔗 Link: {args.strip()}\n\n"
        f"O post será processado em breve."
    )
    
    # Dispara o workflow do GitHub Actions (se configurado)
    trigger_github_workflow()
    
    return "created"


def handle_post_video(chat_id: str, args: str) -> str:
    """Cria requisição de post com vídeo simplificado."""
    parts = args.split()
    
    if not parts:
        send_message(chat_id, "❌ Por favor, envie o link do vídeo do X (Twitter).")
        return "missing_args"

    # Busca link do X/Twitter nos argumentos
    video_url = None
    for p in parts:
        if "x.com" in p or "twitter.com" in p:
            video_url = p
            break
    
    if not video_url:
        send_message(chat_id, "❌ Não encontrei um link do X (Twitter) válido.")
        return "invalid_link"

    # Limpa o link do X (remove trackers)
    if "?" in video_url:
        video_url = video_url.split("?")[0]
    
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    request = {
        "id": request_id,
        "type": "video",
        "article_url": video_url,  # Usamos o link do X como referência
        "video_url": video_url,
        "duration": 15,            # Duração padrão para o modo simplificado
        "created_at": datetime.now().isoformat(),
        "chat_id": chat_id,
        "status": "pending",
        "simplified": True
    }
    
    request_file = QUEUE_DIR / f"request_{request_id}.json"
    with open(request_file, "w", encoding="utf-8") as f:
        json.dump(request, f, indent=2, ensure_ascii=False)
    
    send_message(
        chat_id,
        f"✅ *Vídeo detectado!*\n\n"
        f"📋 ID: `{request_id}`\n"
        f"🎬 Link: {video_url}\n\n"
        f"O vídeo será gerado automaticamente em ~3 minutos via GitHub Actions."
    )
    
    trigger_github_workflow()
    
    return "created"


def handle_status(chat_id: str) -> str:
    """Mostra status da fila."""
    pending_files = list(QUEUE_DIR.glob("request_*.json"))
    
    if not pending_files:
        send_message(chat_id, "✅ Nenhum post na fila.")
        return "empty"
    
    foto_count = 0
    video_count = 0
    
    for file in pending_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                request = json.load(f)
                if request.get("status") == "pending":
                    if request.get("type") == "foto":
                        foto_count += 1
                    else:
                        video_count += 1
        except Exception:
            continue
    
    total = foto_count + video_count
    
    status_text = f"""
📊 *Status da Fila*

📸 Posts com foto: {foto_count}
🎥 Posts com vídeo: {video_count}
📦 Total: {total}
"""
    send_message(chat_id, status_text)
    
    return "success"


def trigger_github_workflow():
    """
    Dispara o workflow do GitHub Actions via repository_dispatch.
    
    Requer:
    - GITHUB_TOKEN com permissão de actions
    - Nome do repositório (owner/repo)
    """
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPOSITORY")  # formato: owner/repo
    
    if not github_token or not github_repo:
        print("⚠️ GitHub token ou repo não configurado")
        return False
    
    url = f"https://api.github.com/repos/{github_repo}/dispatches"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"event_type": "telegram_request"}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 204:
            print("✅ Workflow disparado")
            return True
        else:
            print(f"⚠️ Erro ao disparar workflow: {response.status_code}")
            return False
    except Exception as e:
        print(f"⚠️ Erro: {e}")
        return False


# Flask app para receber webhooks (opcional)
try:
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    
    @app.route("/webhook", methods=["POST"])
    def webhook():
        """Endpoint que recebe atualizações do Telegram."""
        update = request.get_json()
        result = handle_webhook_update(update)
        return jsonify(result)
    
    @app.route("/health", methods=["GET"])
    def health():
        """Health check."""
        return jsonify({"status": "ok", "service": "telegram-webhook"})
    
    def run_webhook_server(host: str = "0.0.0.0", port: int = 8080):
        """Inicia o servidor de webhook."""
        print(f"🚀 Servidor webhook iniciado em {host}:{port}")
        app.run(host=host, port=port)

except ImportError:
    print("⚠️ Flask não instalado. Webhook mode não disponível.")
    print("   Instale com: pip install flask")


def main():
    """Menu principal."""
    import sys
    
    if len(sys.argv) < 2:
        print("""
🔗 Telegram Webhook Manager

Comandos:
    set <url>     - Configura webhook
    delete        - Remove webhook
    info          - Mostra informações do webhook
    server        - Inicia servidor local (Flask)

Exemplos:
    python scripts/telegram_webhook.py set https://seu-dominio.com/webhook
    python scripts/telegram_webhook.py info
    python scripts/telegram_webhook.py server
""")
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    if command == "set":
        if len(sys.argv) < 3:
            print("❌ Forneça a URL do webhook")
            sys.exit(1)
        set_webhook(sys.argv[2])
    
    elif command == "delete":
        delete_webhook()
    
    elif command == "info":
        info = get_webhook_info()
        print("\n📋 Informações do Webhook:")
        print(json.dumps(info, indent=2))
    
    elif command == "server":
        try:
            run_webhook_server()
        except NameError:
            print("❌ Flask não instalado")
            sys.exit(1)
    
    else:
        print(f"❌ Comando desconhecido: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
