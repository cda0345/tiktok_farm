#!/bin/bash
# Script rápido para iniciar o bot do Telegram

echo "🤖 Iniciando @Gossip_personal_bot"
echo "=================================="
echo ""
echo "✅ Bot configurado e pronto!"
echo "📱 Telegram: @Gossip_personal_bot"
echo "🔗 Link: https://t.me/Gossip_personal_bot"
echo ""
echo "💡 Comandos disponíveis no Telegram:"
echo "   /post_foto <link_materia>"
echo "   /post_video <link_materia> <link_video_x> <duracao>"
echo "   /status"
echo "   /help"
echo ""
echo "🚀 Iniciando bot..."
echo ""

cd "$(dirname "$0")"
python3 scripts/telegram_bot.py
