#!/usr/bin/env python3
import os
import json
import requests
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
QUEUE_DIR = ROOT_DIR / "telegram_queue"
QUEUE_DIR.mkdir(exist_ok=True)
ID_FILE = QUEUE_DIR / "last_update_id.txt"

# Token via env var
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def send_message(chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
        return response.status_code == 200
    except Exception:
        return False


def find_existing_request(chat_id: str, video_url: str) -> str | None:
    for req_file in sorted(QUEUE_DIR.glob("request_*.json"), reverse=True):
        try:
            req = json.loads(req_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        if (
            str(req.get("chat_id", "")) == chat_id
            and str(req.get("video_url", "")).strip() == video_url
            and str(req.get("status", "")).strip() in {"pending", "processing"}
        ):
            return str(req.get("id", "")).strip() or None
    return None

def get_last_id():
    if ID_FILE.exists():
        try:
            return int(ID_FILE.read_text().strip())
        except:
            return 0
    return 0

def save_last_id(update_id):
    ID_FILE.write_text(str(update_id))

def poll():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN não configurado.")
        return 0

    last_id = get_last_id()
    print(f"🔍 Buscando mensagens a partir do ID: {last_id}")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": last_id + 1, "timeout": 20}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            print(f"❌ Erro na API do Telegram: {response.text}")
            return
            
        updates = response.json().get("result", [])
        print(f"📩 {len(updates)} novas atualizações encontradas")
        
        new_requests = 0
        for update in updates:
            update_id = update["update_id"]
            save_last_id(update_id)
            
            if "message" not in update:
                continue
                
            msg = update["message"]
            text = msg.get("text", "").strip()
            chat_id = str(msg["chat"]["id"])
            
            # Só aceita links do X ou comando post_video
            if "x.com" in text or "twitter.com" in text:
                # Extrai o link (caso tenha texto antes ou depois)
                words = text.split()
                video_url = None
                for w in words:
                    if "x.com" in w or "twitter.com" in w:
                        video_url = w
                        break
                
                if video_url:
                    if "?" in video_url:
                        video_url = video_url.split("?")[0]

                    existing_id = find_existing_request(chat_id, video_url)
                    if existing_id:
                        send_message(
                            chat_id,
                            (
                                f"🔁 Link já está na fila (ID: {existing_id}).\n"
                                "⚡ Processamento em andamento, não precisa reenviar."
                            ),
                        )
                        continue
                    
                    request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    req = {
                        "id": request_id,
                        "type": "video",
                        "video_url": video_url,
                        "article_url": video_url,
                        "duration": 15,
                        "created_at": datetime.now().isoformat(),
                        "chat_id": chat_id,
                        "status": "pending",
                        "source": "github_actions_poll"
                    }
                    
                    with open(QUEUE_DIR / f"request_{request_id}.json", "w") as f:
                        json.dump(req, f, indent=2)
                    
                    print(f"✅ Requisição {request_id} salva!")
                    send_message(
                        chat_id,
                        (
                            f"✅ Link recebido! ID: {request_id}\n"
                            "⚡ Vou processar agora. Não precisa enviar o link de novo."
                        ),
                    )
                    new_requests += 1
        
        return new_requests
                
    except Exception as e:
        print(f"⚠️ Erro ao colher mensagens: {e}")
        return 0

if __name__ == "__main__":
    poll()
