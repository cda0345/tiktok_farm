#!/usr/bin/env python3
"""
Bot Telegram para receber requisições de posts via mensagem.

Fluxo:
1. Usuário envia comando /post_foto ou /post_video
2. Bot responde pedindo o link da matéria
3. Para vídeos, pede também o link do vídeo do X e duração
4. Salva requisição em arquivo JSON
5. GitHub Actions processa a fila

Comandos:
/post_foto <link_materia> - Cria post com foto e matéria
/post_video <link_materia> <link_video_x> <duracao_segundos> - Cria post com vídeo
/status - Mostra quantos posts estão na fila
/help - Mostra ajuda
"""

import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import requests

# Diretório de requisições
ROOT_DIR = Path(__file__).resolve().parents[1]
QUEUE_DIR = ROOT_DIR / "telegram_queue"
QUEUE_DIR.mkdir(exist_ok=True)

# Configurações do Telegram
# Usando o bot já configurado no projeto
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8519683231:AAH1RsrgaYmo3v99hd_yfktgoFWHU2AWrP0"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "1015015823"


class TelegramBot:
    """Bot para receber requisições via Telegram."""
    
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.last_update_id = 0
    
    def push_to_github(self, request_id: str) -> bool:
        """Faz push automático da requisição para o GitHub."""
        try:
            print(f"\n🔄 Fazendo push da requisição {request_id} para o GitHub...")
            
            # Git Add
            subprocess.run(["git", "add", "telegram_queue/"], cwd=ROOT_DIR, capture_output=True)
            
            # Git Commit
            commit_msg = f"feat: nova requisição via Telegram ({request_id})"
            result = subprocess.run(["git", "commit", "-m", commit_msg], cwd=ROOT_DIR, capture_output=True, text=True)
            
            if result.returncode != 0 and "nothing to commit" not in result.stdout:
                print(f"⚠️ Erro no commit: {result.stderr}")
                return False
            
            # Git Push
            print("📤 Enviando para o GitHub...")
            result = subprocess.run(["git", "push"], cwd=ROOT_DIR, capture_output=True, timeout=30)
            
            if result.returncode == 0:
                print("✅ Push realizado com sucesso!")
                return True
            else:
                print(f"⚠️ Erro no push: {result.stderr}")
                return False
        except Exception as e:
            print(f"⚠️ Erro ao fazer push: {e}")
            return False

    def send_message(self, chat_id: str, text: str) -> bool:
        """Envia mensagem de texto para o chat."""
        url = f"{self.api_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=data, timeout=30)
            return response.status_code == 200
        except Exception as e:
            print(f"Erro ao enviar mensagem: {e}")
            return False
    
    def get_updates(self, offset: int = 0) -> List[Dict[str, Any]]:
        """Busca novas mensagens."""
        url = f"{self.api_url}/getUpdates"
        params = {"offset": offset, "timeout": 30}
        try:
            response = requests.get(url, params=params, timeout=35)
            if response.status_code == 200:
                data = response.json()
                return data.get("result", [])
        except Exception as e:
            print(f"Erro ao buscar updates: {e}")
        return []
    
    def process_message(self, message: Dict[str, Any]) -> None:
        """Processa uma mensagem recebida."""
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()
        
        if not text:
            return
        
        # Processa comandos
        if text.startswith("/"):
            self.handle_command(chat_id, text)
        
    def handle_command(self, chat_id: str, text: str) -> None:
        """Processa comandos do bot."""
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if command == "/start" or command == "/help":
            self.send_help(chat_id)
        
        elif command == "/post_foto":
            self.handle_post_foto(chat_id, args)
        
        elif command == "/post_video":
            self.handle_post_video(chat_id, args)
        
        elif command == "/status":
            self.handle_status(chat_id)
        
        else:
            self.send_message(chat_id, "❌ Comando desconhecido. Use /help para ver os comandos disponíveis.")
    
    def send_help(self, chat_id: str) -> None:
        """Envia mensagem de ajuda."""
        help_text = """
🤖 *Bot de Criação de Posts*

*Comandos disponíveis:*

📸 `/post_foto <link_materia>`
Cria um post com foto e matéria

Exemplo:
```
/post_foto https://contigo.com.br/noticias/fulano-beltrano-se-separam
```

🎥 `/post_video <link_materia> <link_video_x> <duracao>`
Cria um post com vídeo do X

Exemplo:
```
/post_video https://contigo.com.br/noticias/treta-bbb https://x.com/fulano/status/123456 15
```

📊 `/status`
Mostra quantos posts estão na fila

❓ `/help`
Mostra esta mensagem
"""
        self.send_message(chat_id, help_text)
    
    def handle_post_foto(self, chat_id: str, args: str) -> None:
        """Cria requisição de post com foto."""
        if not args or not args.startswith("http"):
            self.send_message(
                chat_id,
                "❌ Por favor, forneça o link da matéria.\n\n"
                "Exemplo: `/post_foto https://contigo.com.br/noticias/sua-materia`"
            )
            return
        
        # Cria requisição
        request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        request = {
            "id": request_id,
            "type": "foto",
            "article_url": args.strip(),
            "created_at": datetime.now().isoformat(),
            "chat_id": chat_id,
            "status": "pending"
        }
        
        # Salva em arquivo
        request_file = QUEUE_DIR / f"request_{request_id}.json"
        with open(request_file, "w", encoding="utf-8") as f:
            json.dump(request, f, indent=2, ensure_ascii=False)
        
        # AUTO-PUSH
        pushed = self.push_to_github(request_id)
        
        msg = f"✅ *Requisição criada!*\n\n📋 ID: `{request_id}`\n📸 Tipo: Post com foto\n"
        if pushed:
            msg += "\n🚀 *Enviado para o GitHub!*\nO vídeo chegará aqui em ~3 minutos."
        else:
            msg += "\n⚠️ Erro ao enviar para o GitHub. O processamento pode atrasar."
            
        self.send_message(chat_id, msg)

    def handle_post_video(self, chat_id: str, args: str) -> None:
        """Cria requisição de post com vídeo."""
        parts = args.split()
        
        if len(parts) < 3:
            self.send_message(
                chat_id,
                "❌ Formato incorreto.\n\n"
                "Use: `/post_video <link_materia> <link_video_x> <duracao_segundos>`\n\n"
                "Exemplo:\n"
                "`/post_video https://contigo.com.br/news https://x.com/user/status/123 15`"
            )
            return
        
        article_url = parts[0]
        video_url = parts[1]
        
        try:
            duration = int(parts[2])
            if duration < 5 or duration > 60:
                raise ValueError("Duração deve estar entre 5 e 60 segundos")
        except ValueError as e:
            self.send_message(
                chat_id,
                f"❌ Duração inválida: {e}\n\n"
                "Use um número entre 5 e 60 segundos."
            )
            return
        
        if not article_url.startswith("http") or not video_url.startswith("http"):
            self.send_message(chat_id, "❌ Os links devem começar com http:// ou https://")
            return
        
        # Cria requisição
        request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        request = {
            "id": request_id,
            "type": "video",
            "article_url": article_url,
            "video_url": video_url,
            "duration": duration,
            "created_at": datetime.now().isoformat(),
            "chat_id": chat_id,
            "status": "pending"
        }
        
        # Salva em arquivo
        request_file = QUEUE_DIR / f"request_{request_id}.json"
        with open(request_file, "w", encoding="utf-8") as f:
            json.dump(request, f, indent=2, ensure_ascii=False)
        
        # AUTO-PUSH
        pushed = self.push_to_github(request_id)
        
        msg = f"✅ *Requisição criada!*\n\n📋 ID: `{request_id}`\n🎥 Tipo: Vídeo\n"
        if pushed:
            msg += "\n🚀 *Enviado para o GitHub!*\nO vídeo chegará aqui em ~3 minutos."
        else:
            msg += "\n⚠️ Erro ao enviar para o GitHub. O processamento pode atrasar."
            
        self.send_message(chat_id, msg)
    
    def handle_status(self, chat_id: str) -> None:
        """Mostra status da fila."""
        pending_files = list(QUEUE_DIR.glob("request_*.json"))
        
        if not pending_files:
            self.send_message(chat_id, "✅ Nenhum post na fila.")
            return
        
        # Conta por tipo
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

Os posts serão processados pelo GitHub Actions.
"""
        self.send_message(chat_id, status_text)
    
    def run_polling(self) -> None:
        """Inicia o bot em modo polling."""
        print("🤖 Bot iniciado. Aguardando mensagens...")
        print(f"📁 Fila em: {QUEUE_DIR}")
        
        while True:
            try:
                updates = self.get_updates(offset=self.last_update_id + 1)
                
                for update in updates:
                    self.last_update_id = update["update_id"]
                    
                    if "message" in update:
                        self.process_message(update["message"])
                
            except KeyboardInterrupt:
                print("\n👋 Bot finalizado.")
                break
            except Exception as e:
                print(f"⚠️ Erro no polling: {e}")
                import time
                time.sleep(5)


def main():
    """Função principal."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("❌ Configure TELEGRAM_BOT_TOKEN no ambiente ou no script")
        sys.exit(1)
    
    bot = TelegramBot(TELEGRAM_BOT_TOKEN)
    bot.run_polling()


if __name__ == "__main__":
    main()
