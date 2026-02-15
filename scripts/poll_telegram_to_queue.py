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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8519683231:AAH1RsrgaYmo3v99hd_yfktgoFWHU2AWrP0"

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
                    new_requests += 1
        
        return new_requests
                
    except Exception as e:
        print(f"⚠️ Erro ao colher mensagens: {e}")
        return 0

if __name__ == "__main__":
    poll()
