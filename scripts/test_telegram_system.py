#!/usr/bin/env python3
"""
Script de teste para simular uma requisição do Telegram sem usar o bot.
Útil para testar o processamento localmente.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
QUEUE_DIR = ROOT_DIR / "telegram_queue"
QUEUE_DIR.mkdir(exist_ok=True)


def create_test_foto_request():
    """Cria uma requisição de teste para post com foto."""
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    request = {
        "id": request_id,
        "type": "foto",
        "article_url": "https://contigo.com.br/noticias/novidades/veja-como-esta-o-elenco-de-malhacao-sonhos-anos-depois-do-fim-da-novela",
        "created_at": datetime.now().isoformat(),
        "chat_id": "1015015823",
        "status": "pending"
    }
    
    request_file = QUEUE_DIR / f"request_{request_id}.json"
    with open(request_file, "w", encoding="utf-8") as f:
        json.dump(request, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Requisição de teste criada: {request_file}")
    print(f"📋 ID: {request_id}")
    print(f"📸 Tipo: Post com foto")
    print(f"\n🔄 Execute para processar:")
    print(f"   python scripts/process_telegram_queue.py")


def create_test_video_request():
    """Cria uma requisição de teste para post com vídeo."""
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    request = {
        "id": request_id,
        "type": "video",
        "article_url": "https://contigo.com.br/noticias/novidades/bbb-treta-fulano-beltrano",
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Vídeo de teste
        "duration": 10,
        "created_at": datetime.now().isoformat(),
        "chat_id": "1015015823",
        "status": "pending"
    }
    
    request_file = QUEUE_DIR / f"request_{request_id}.json"
    with open(request_file, "w", encoding="utf-8") as f:
        json.dump(request, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Requisição de vídeo criada: {request_file}")
    print(f"📋 ID: {request_id}")
    print(f"🎥 Tipo: Post com vídeo")
    print(f"\n🔄 Execute para processar:")
    print(f"   python scripts/process_telegram_queue.py")


def list_queue():
    """Lista todas as requisições na fila."""
    pending_files = sorted(QUEUE_DIR.glob("request_*.json"))
    
    if not pending_files:
        print("📭 Fila vazia")
        return
    
    print(f"\n📦 {len(pending_files)} requisições na fila:\n")
    
    for request_file in pending_files:
        try:
            with open(request_file, "r", encoding="utf-8") as f:
                request = json.load(f)
            
            status_emoji = {
                "pending": "⏳",
                "processing": "🔄",
                "completed": "✅",
                "failed": "❌"
            }.get(request.get("status"), "❓")
            
            print(f"{status_emoji} {request['id']}")
            print(f"   Tipo: {request['type']}")
            print(f"   Status: {request['status']}")
            print(f"   Criado: {request['created_at']}")
            
            if request['type'] == 'video':
                print(f"   Duração: {request.get('duration')}s")
            
            print()
            
        except Exception as e:
            print(f"⚠️  Erro ao ler {request_file.name}: {e}\n")


def clear_completed():
    """Remove requisições completadas da fila."""
    pending_files = list(QUEUE_DIR.glob("request_*.json"))
    removed = 0
    
    for request_file in pending_files:
        try:
            with open(request_file, "r", encoding="utf-8") as f:
                request = json.load(f)
            
            if request.get("status") in ["completed", "failed"]:
                request_file.unlink()
                removed += 1
                print(f"🗑️  Removido: {request_file.name}")
        
        except Exception as e:
            print(f"⚠️  Erro ao processar {request_file.name}: {e}")
    
    if removed == 0:
        print("✅ Nenhuma requisição completada para remover")
    else:
        print(f"\n✅ {removed} requisição(ões) removida(s)")


def main():
    """Menu principal."""
    if len(sys.argv) < 2:
        print("""
🧪 Teste do Sistema de Posts via Telegram

Uso:
    python scripts/test_telegram_system.py [comando]

Comandos:
    foto        - Cria requisição de teste com foto
    video       - Cria requisição de teste com vídeo
    list        - Lista todas as requisições na fila
    clear       - Remove requisições completadas
    process     - Processa a fila (atalho)

Exemplos:
    python scripts/test_telegram_system.py foto
    python scripts/test_telegram_system.py list
    python scripts/test_telegram_system.py process
""")
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    if command == "foto":
        create_test_foto_request()
    
    elif command == "video":
        create_test_video_request()
    
    elif command == "list":
        list_queue()
    
    elif command == "clear":
        clear_completed()
    
    elif command == "process":
        print("🔄 Processando fila...\n")
        import subprocess
        result = subprocess.run(
            ["python", "scripts/process_telegram_queue.py"],
            cwd=ROOT_DIR
        )
        sys.exit(result.returncode)
    
    else:
        print(f"❌ Comando desconhecido: {command}")
        print("Use: foto, video, list, clear, ou process")
        sys.exit(1)


if __name__ == "__main__":
    main()
