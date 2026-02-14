#!/bin/bash
# Script para rodar o bot do Telegram localmente

echo "🤖 Iniciando Bot do Telegram"
echo "================================"
echo ""

# Verifica se as variáveis de ambiente estão configuradas
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "⚠️  TELEGRAM_BOT_TOKEN não configurado"
    echo "Configure com: export TELEGRAM_BOT_TOKEN='seu_token'"
    echo ""
fi

if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "⚠️  TELEGRAM_CHAT_ID não configurado"
    echo "Configure com: export TELEGRAM_CHAT_ID='seu_chat_id'"
    echo ""
fi

# Verifica se as dependências estão instaladas
if ! python3 -c "import requests" 2>/dev/null; then
    echo "📦 Instalando dependências..."
    pip3 install -r requirements.txt
fi

# Inicia o bot
echo "✅ Iniciando bot..."
echo ""
python3 scripts/telegram_bot.py
