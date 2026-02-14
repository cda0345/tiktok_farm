#!/bin/bash
# Script para iniciar bot com AUTO-PUSH para GitHub

echo "🚀 Bot do Telegram com AUTO-PUSH"
echo "=================================="
echo ""
echo "✅ Bot: @Gossip_personal_bot"
echo "✅ Modo: Push automático para GitHub"
echo ""
echo "💡 Como funciona:"
echo "   1. Você envia comando no Telegram"
echo "   2. Bot cria requisição"
echo "   3. Bot faz push automático para GitHub"
echo "   4. GitHub Actions processa (~2-3 min)"
echo "   5. Vídeo chega no seu Telegram!"
echo ""
echo "📱 Comandos disponíveis:"
echo "   /post_foto <link>"
echo "   /post_video <link_materia> <link_video_x> <duracao>"
echo "   /status"
echo ""
echo "🔄 Iniciando bot com auto-push..."
echo ""

cd "$(dirname "$0")"
python3 scripts/telegram_bot_autopush.py
