#!/usr/bin/env python3
"""
Processador SIMPLIFICADO de requisições da fila do Telegram.
Versão que chama create_gossip_post.py diretamente.
"""

import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
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


def process_foto_request(request: Dict[str, Any]) -> bool:
    """Processa requisição de post com foto chamando create_gossip_post.py."""
    print(f"\n📸 Processando post com foto: {request['id']}")
    print(f"🔗 Link: {request['article_url']}")
    
    chat_id = request["chat_id"]
    
    # Notifica início
    send_message(chat_id, f"🔄 Processando post `{request['id']}`...")
    
    try:
        # Chama create_gossip_post.py para gerar UM post
        print("📰 Executando create_gossip_post.py...")
        
        result = subprocess.run(
            [
                sys.executable,  # Usa o Python atual
                str(ROOT_DIR / "scripts" / "create_gossip_post.py"),
                "--profile", "br",
                "--count", "1"
            ],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=180  # 3 minutos
        )
        
        print(f"Return code: {result.returncode}")
        print(f"STDOUT: {result.stdout[:500]}")  # Primeiros 500 chars
        if result.stderr:
            print(f"STDERR: {result.stderr[:500]}")
        
        if result.returncode == 0:
            send_message(chat_id, f"✅ Post `{request['id']}` criado!\n\nVídeo será enviado em breve.")
            return True
        else:
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
    send_message(chat_id, f"⚠️ Posts com vídeo ainda não implementados. Post `{request['id']}` ignorado.")
    
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
            
            # Marca como processando
            request["status"] = "processing"
            request["processing_started"] = datetime.now().isoformat()
            with open(request_file, "w", encoding="utf-8") as f:
                json.dump(request, f, indent=2, ensure_ascii=False)
            
            # Processa baseado no tipo
            success = False
            if request["type"] == "foto":
                success = process_foto_request(request)
            elif request["type"] == "video":
                success = process_video_request(request)
            
            # Atualiza status
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


def main():
    """Função principal."""
    print("🚀 Iniciando processador de requisições do Telegram")
    print(f"📁 Fila em: {QUEUE_DIR}")
    
    processed = process_queue()
    
    if processed > 0:
        print(f"\n🎉 {processed} post(s) criado(s) com sucesso!")
    else:
        print("\n📭 Nenhum post foi processado.")


if __name__ == "__main__":
    main()
