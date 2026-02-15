#!/bin/bash
# Script oficial para iniciar o bot do Telegram com AUTO-PUSH

echo "🚀 Iniciando Bot Gossip Shorts (Modo: Auto-Push Ativo)"
echo "====================================================="
echo ""

# Verifica se o diretório da fila existe
mkdir -p telegram_queue

# Inicia o bot principal (que agora já faz push automático)
cd "$(dirname "$0")"
python3 scripts/telegram_bot.py
