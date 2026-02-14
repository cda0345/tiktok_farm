# 🚀 Quick Start - Sistema de Posts via Telegram

## Setup Rápido (5 minutos)

### 1. Crie seu Bot no Telegram

1. Abra o Telegram e fale com [@BotFather](https://t.me/BotFather)
2. Envie `/newbot`
3. Escolha um nome (ex: "Meu Gossip Bot")
4. Escolha um username (ex: "meugossipbot")
5. **Copie o token** que ele te dá (ex: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Descubra seu Chat ID

1. Envie uma mensagem para [@userinfobot](https://t.me/userinfobot)
2. Ele vai te mostrar seu ID (ex: `1015015823`)

### 3. Configure no GitHub

1. Vá em: `Settings` → `Secrets and variables` → `Actions`
2. Clique em `New repository secret`
3. Adicione:
   - Name: `TELEGRAM_BOT_TOKEN`, Value: `seu_token_aqui`
   - Name: `TELEGRAM_CHAT_ID`, Value: `seu_chat_id_aqui`

### 4. Teste Localmente (Opcional)

```bash
# Configure as variáveis
export TELEGRAM_BOT_TOKEN="seu_token"
export TELEGRAM_CHAT_ID="seu_chat_id"

# Execute o bot
./run_telegram_bot.sh
```

Agora envie `/start` para seu bot no Telegram!

### 5. Use!

No Telegram, envie:

```
/post_foto https://contigo.com.br/noticias/sua-materia
```

Ou para vídeo:

```
/post_video https://contigo.com.br/news https://x.com/fulano/status/123 15
```

O bot vai confirmar e o GitHub Actions vai processar em até 15 minutos!

## 📱 Comandos Disponíveis

- `/post_foto <link>` - Post com foto da matéria
- `/post_video <link_materia> <link_video_x> <segundos>` - Post com vídeo do X
- `/status` - Ver fila de posts
- `/help` - Ajuda completa

## 🔧 Troubleshooting

**Bot não responde?**
- Envie `/start` primeiro
- Verifique se o token está correto
- Certifique-se que o bot não está bloqueado

**Posts não são criados?**
- Verifique os secrets no GitHub
- Veja os logs em Actions
- Aguarde até 15 minutos (cron do workflow)

**Quer processar imediatamente?**
- Vá em Actions → Process Telegram Queue → Run workflow

## 📚 Documentação Completa

Veja [TELEGRAM_BOT_GUIDE.md](TELEGRAM_BOT_GUIDE.md) para mais detalhes.

## 🎯 Exemplos Reais

### Criar post sobre BBB
```
/post_foto https://gshow.globo.com/realities/bbb/bbb-25/noticia/fulano-e-beltrano-brigam-no-bbb25.ghtml
```

### Criar post com vídeo de treta
```
/post_video https://contigo.com.br/bbb-treta https://x.com/redebbbnews/status/1234567 12
```

## ⚡ Dicas

- Você pode enviar vários comandos seguidos
- A fila processa todos os posts em ordem
- Use `/status` para ver o progresso
- Posts prontos são enviados de volta para você no Telegram

---

**Pronto!** Agora você pode criar posts apenas enviando mensagens no Telegram! 🎉
