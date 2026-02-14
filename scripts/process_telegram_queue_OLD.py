#!/usr/bin/env python3
"""
Processador de requisições da fila do Telegram.
Executado pelo GitHub Actions para processar posts criados via bot.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Importa apenas o que existe e funciona
from scripts import create_gossip_post

QUEUE_DIR = ROOT_DIR / "telegram_queue"
QUEUE_DIR.mkdir(exist_ok=True)

# Configurações do Telegram - usando bot já configurado
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8519683231:AAH1RsrgaYmo3v99hd_yfktgoFWHU2AWrP0"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "1015015823"


def _send_video_to_telegram(video_path: Path, caption: str) -> bool:
    """Envia vídeo para o Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    try:
        with open(video_path, "rb") as video:
            files = {"video": video}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
            response = requests.post(url, files=files, data=data, timeout=120)
            if response.status_code == 200:
                print(f"✅ Vídeo enviado com sucesso para o Telegram!")
                return True
            else:
                print(f"❌ Erro ao enviar para o Telegram: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        print(f"⚠️ Falha ao tentar enviar para o Telegram: {e}")
        return False


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


def download_video_from_x(video_url: str, output_path: Path) -> bool:
    """
    Baixa vídeo do X (Twitter).
    Nota: Pode precisar de API específica ou ferramenta como yt-dlp.
    """
    try:
        # Tenta usar yt-dlp se disponível
        import subprocess
        
        cmd = [
            "yt-dlp",
            "-f", "best[ext=mp4]",
            "-o", str(output_path),
            video_url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and output_path.exists():
            print(f"✅ Vídeo baixado: {output_path}")
            return True
        else:
            print(f"❌ Erro ao baixar vídeo: {result.stderr}")
            return False
            
    except ImportError:
        print("⚠️ yt-dlp não instalado. Use: pip install yt-dlp")
        return False
    except Exception as e:
        print(f"❌ Erro ao baixar vídeo do X: {e}")
        return False


def process_foto_request(request: Dict[str, Any]) -> bool:
    """Processa requisição de post com foto."""
    print(f"\n📸 Processando post com foto: {request['id']}")
    print(f"🔗 Link: {request['article_url']}")
    
    article_url = request["article_url"]
    chat_id = request["chat_id"]
    
    # Notifica início
    send_message(chat_id, f"🔄 Processando post `{request['id']}`...")
    
    try:
        # Usa a função main do create_gossip_post diretamente
        print("📰 Executando create_gossip_post.main()...")
        
        # Configura argumentos temporários
        import sys
        old_argv = sys.argv
        sys.argv = [
            "create_gossip_post.py",
            "--profile", "br",
            "--count", "1"
        ]
        
        try:
            # Executa o main do create_gossip_post
            create_gossip_post.main()
            
            # Restaura argv
            sys.argv = old_argv
            
            send_message(chat_id, f"✅ Post `{request['id']}` criado com sucesso!")
            return True
            
        except Exception as e:
            sys.argv = old_argv
            raise e
        
    except Exception as e:
        error_msg = f"❌ Erro ao processar post: {e}"
        print(error_msg)
        send_message(chat_id, error_msg)
        return False
            timeout=180
        )
        
        if result.returncode == 0:
            print("✅ Post criado com sucesso!")
            print(result.stdout)
            send_message(chat_id, f"✅ Post `{request['id']}` criado e enviado!")
            return True
        else:
            print(f"❌ Erro ao criar post: {result.stderr}")
            send_message(chat_id, f"❌ Erro ao processar post `{request['id']}`")
            return False
        
    except Exception as e:
        error_msg = f"❌ Erro ao processar post: {e}"
        print(error_msg)
        send_message(chat_id, error_msg)
        return False


def process_video_request(request: Dict[str, Any]) -> bool:
    """Processa requisição de post com vídeo."""
    print(f"\n🎥 Processando post com vídeo: {request['id']}")
    print(f"🔗 Matéria: {request['article_url']}")
    print(f"🎬 Vídeo X: {request['video_url']}")
    print(f"⏱ Duração: {request['duration']}s")
    
    chat_id = request["chat_id"]
    
    # Notifica início
    send_message(chat_id, f"🔄 Processando post com vídeo `{request['id']}`...")
    
    try:
        # Baixa vídeo do X
        gossip_dir = ROOT_DIR / "gossip_post"
        gossip_dir.mkdir(exist_ok=True)
        
        video_path = gossip_dir / f"video_x_{request['id']}.mp4"
        
        print("📥 Baixando vídeo do X...")
        if not download_video_from_x(request['video_url'], video_path):
            raise Exception("Falha ao baixar vídeo do X")
        
        # Busca título da matéria
        headers = {"User-Agent": "Mozilla/5.0 (compatible; GossipPostBot/1.0)"}
        response = requests.get(request['article_url'], headers=headers, timeout=30)
        html = response.text
        
        import re
        title_match = re.search(r"<title>([^<]+)</title>", html, re.I)
        title = title_match.group(1) if title_match else "Notícia"
        
        # Corta vídeo na duração especificada
        from core.ffmpeg_utils import ensure_ffmpeg, run_ffmpeg
        
        ff = ensure_ffmpeg("tools")
        duration = request['duration']
        
        trimmed_video = gossip_dir / f"video_trimmed_{request['id']}.mp4"
        
        print(f"✂️ Cortando vídeo para {duration}s...")
        cmd = [
            str(ff),
            "-i", str(video_path),
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-y",
            str(trimmed_video)
        ]
        
        run_ffmpeg(cmd)
        
        # Adiciona headline e overlay (simplificado)
        headline_file = gossip_dir / "headline.txt"
        with open(headline_file, "w", encoding="utf-8") as f:
            f.write(title[:100])
        
        output_video = gossip_dir / "output" / f"post_video_{request['id']}.mp4"
        output_video.parent.mkdir(exist_ok=True)
        
        # Por enquanto, usa vídeo cortado diretamente
        # TODO: Adicionar overlay de texto sobre o vídeo
        import shutil
        shutil.copy(trimmed_video, output_video)
        
        # Envia para o Telegram
        caption = f"{title[:200]}\n\n📰 {request['article_url']}"
        _send_video_to_telegram(output_video, caption)
        
        send_message(chat_id, f"✅ Post com vídeo `{request['id']}` criado com sucesso!")
        
        return True
        
    except Exception as e:
        error_msg = f"❌ Erro ao processar post com vídeo: {e}"
        print(error_msg)
        send_message(chat_id, error_msg)
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
