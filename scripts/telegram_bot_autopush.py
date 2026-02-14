#!/usr/bin/env python3
"""
Bot do Telegram com PUSH AUTOMÁTICO para o GitHub.
Quando você envia um comando, o bot automaticamente faz push da requisição.
"""

import os
import sys
import subprocess
from pathlib import Path

# Adiciona o diretório raiz ao path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.telegram_bot import TelegramBot, TELEGRAM_BOT_TOKEN, QUEUE_DIR


class AutoPushBot(TelegramBot):
    """Bot que faz push automático das requisições para o GitHub."""
    
    def push_to_github(self, request_id: str) -> bool:
        """
        Faz push automático da requisição para o GitHub.
        Isso dispara o workflow automaticamente!
        """
        try:
            print(f"\n🔄 Fazendo push da requisição {request_id} para o GitHub...")
            
            # Add
            result = subprocess.run(
                ["git", "add", "telegram_queue/"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"⚠️ Erro no git add: {result.stderr}")
                return False
            
            # Commit
            commit_msg = f"feat: nova requisição de post via Telegram ({request_id})"
            result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                # Pode ser que não tenha mudanças
                if "nothing to commit" in result.stdout:
                    print("✅ Sem mudanças para commitar")
                else:
                    print(f"⚠️ Erro no git commit: {result.stderr}")
                return False
            
            # Push
            result = subprocess.run(
                ["git", "push"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                print(f"⚠️ Erro no git push: {result.stderr}")
                return False
            
            print(f"✅ Push realizado! GitHub Actions vai processar em ~2-3 minutos")
            return True
            
        except subprocess.TimeoutExpired:
            print("⚠️ Timeout ao fazer push")
            return False
        except Exception as e:
            print(f"⚠️ Erro ao fazer push: {e}")
            return False
    
    def handle_post_foto(self, chat_id: str, args: str) -> None:
        """Cria requisição de post com foto e faz push automático."""
        # Chama a função original
        super().handle_post_foto(chat_id, args)
        
        # Pega o ID da última requisição criada
        request_files = sorted(QUEUE_DIR.glob("request_*.json"))
        if request_files:
            last_request = request_files[-1]
            request_id = last_request.stem.replace("request_", "")
            
            # Faz push automático
            if self.push_to_github(request_id):
                self.send_message(
                    chat_id,
                    f"🚀 Requisição enviada ao GitHub!\n"
                    f"GitHub Actions vai processar em ~2-3 minutos.\n"
                    f"Você receberá o vídeo aqui no Telegram quando ficar pronto!"
                )
    
    def handle_post_video(self, chat_id: str, args: str) -> None:
        """Cria requisição de post com vídeo e faz push automático."""
        # Chama a função original
        super().handle_post_video(chat_id, args)
        
        # Pega o ID da última requisição criada
        request_files = sorted(QUEUE_DIR.glob("request_*.json"))
        if request_files:
            last_request = request_files[-1]
            request_id = last_request.stem.replace("request_", "")
            
            # Faz push automático
            if self.push_to_github(request_id):
                self.send_message(
                    chat_id,
                    f"🚀 Requisição de vídeo enviada ao GitHub!\n"
                    f"GitHub Actions vai processar em ~2-3 minutos.\n"
                    f"Você receberá o vídeo aqui no Telegram quando ficar pronto!"
                )


def main():
    """Função principal."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("❌ Configure TELEGRAM_BOT_TOKEN no ambiente ou no script")
        sys.exit(1)
    
    print("🤖 Bot Telegram com AUTO-PUSH para GitHub")
    print("=" * 50)
    print("✅ Quando você enviar comandos, o bot fará push automático!")
    print("✅ GitHub Actions processará em ~2-3 minutos")
    print("✅ Você receberá os vídeos aqui no Telegram")
    print()
    
    bot = AutoPushBot(TELEGRAM_BOT_TOKEN)
    bot.run_polling()


if __name__ == "__main__":
    main()
