# Sistema de Posts via Telegram

Este sistema permite criar posts de gossip automaticamente enviando comandos via Telegram.

## 📋 Visão Geral

O fluxo funciona assim:
1. Você envia um comando para o bot do Telegram
2. O bot cria uma requisição e salva na fila (`telegram_queue/`)
3. O GitHub Actions processa a fila a cada 15 minutos
4. O vídeo é criado e enviado de volta para o Telegram

## 🤖 Comandos do Bot

### Post com Foto
```
/post_foto https://contigo.com.br/noticias/sua-materia
```
Cria um post estilo TikTok com:
- Foto da matéria
- Headline sobreposta
- Duração de 5 segundos

### Post com Vídeo do X (Twitter)
```
/post_video <link_materia> <link_video_x> <duracao_segundos>
```

Exemplo:
```
/post_video https://contigo.com.br/bbb-treta https://x.com/fulano/status/123456 15
```

Cria um post com:
- Vídeo baixado do X/Twitter
- Cortado na duração especificada
- Headline da matéria sobreposta

### Outros Comandos
```
/status - Mostra quantos posts estão na fila
/help - Mostra ajuda completa
```

## 🚀 Como Usar

### 1. Configure o Bot do Telegram

Se ainda não tem um bot:

1. Abra o Telegram e fale com [@BotFather](https://t.me/BotFather)
2. Envie `/newbot` e siga as instruções
3. Copie o token do bot
4. Configure no GitHub:
   - Vá em Settings → Secrets → Actions
   - Adicione `TELEGRAM_BOT_TOKEN` com o token do bot
   - Adicione `TELEGRAM_CHAT_ID` com seu chat ID (pode obter em @userinfobot)

### 2. Execute o Bot Localmente (Opcional)

Para testar localmente:

```bash
# Configure as variáveis de ambiente
export TELEGRAM_BOT_TOKEN="seu_token"
export TELEGRAM_CHAT_ID="seu_chat_id"

# Execute o bot
python scripts/telegram_bot.py
```

O bot ficará rodando e aguardando mensagens.

### 3. Envie Comandos

Abra o Telegram e envie mensagens para seu bot:

```
/post_foto https://contigo.com.br/noticias/casal-se-separa
```

O bot responderá confirmando a criação da requisição.

### 4. Aguarde o Processamento

O GitHub Actions roda automaticamente a cada 15 minutos e processa todas as requisições pendentes.

Você receberá uma notificação quando o post estiver pronto!

## 📁 Estrutura de Arquivos

```
telegram_queue/
├── request_20260214_143022.json  # Requisição pendente
├── request_20260214_143500.json  # Requisição processada
└── ...
```

Cada requisição é um arquivo JSON com:

```json
{
  "id": "20260214_143022",
  "type": "foto",
  "article_url": "https://...",
  "created_at": "2026-02-14T14:30:22",
  "chat_id": "123456",
  "status": "pending"
}
```

Para posts com vídeo:

```json
{
  "id": "20260214_143500",
  "type": "video",
  "article_url": "https://...",
  "video_url": "https://x.com/...",
  "duration": 15,
  "created_at": "2026-02-14T14:35:00",
  "chat_id": "123456",
  "status": "pending"
}
```

## 🔄 Status das Requisições

- `pending` - Aguardando processamento
- `processing` - Sendo processada
- `completed` - Processada com sucesso
- `failed` - Falhou (você receberá uma mensagem com o erro)

## ⚙️ Configuração do GitHub Actions

O workflow `.github/workflows/telegram_queue.yml` é executado:

1. **A cada 15 minutos** (cron: `*/15 * * * *`)
2. **Manualmente** via workflow_dispatch
3. **Automaticamente** quando um arquivo é adicionado em `telegram_queue/`

### Secrets Necessários

Configure em Settings → Secrets → Actions:

- `TELEGRAM_BOT_TOKEN` - Token do bot do Telegram
- `TELEGRAM_CHAT_ID` - ID do chat para enviar os vídeos
- `OPENAI_API_KEY` - (Já configurado) Para geração de conteúdo

## 🎨 Personalização

### Mudar Duração do Post com Foto

Edite `scripts/process_telegram_queue.py`:

```python
def process_foto_request(request):
    # ...
    _render_short(
        image_path=image_path,
        headline_file=headline_file,
        source="telegram_request",
        out_video=output_video,
        # Adicione parâmetro de duração se disponível
    )
```

### Adicionar Overlay no Vídeo do X

Atualmente o vídeo é apenas cortado. Para adicionar overlays de texto:

```python
# Em process_video_request()
# TODO: Usar ffmpeg para adicionar texto sobre o vídeo
from core.ffmpeg_utils import run_ffmpeg

# Comando ffmpeg para adicionar texto
cmd = [
    "ffmpeg",
    "-i", str(trimmed_video),
    "-vf", f"drawtext=text='{title}':fontsize=40:...",
    str(output_video)
]
run_ffmpeg(cmd)
```

## 🐛 Troubleshooting

### Bot não responde
- Verifique se o token está correto
- Confirme que você enviou `/start` para o bot primeiro

### Posts não são processados
- Verifique os logs do GitHub Actions
- Confirme que os secrets estão configurados corretamente
- Veja se há requisições na pasta `telegram_queue/`

### Vídeo do X não baixa
- Certifique-se que `yt-dlp` está instalado
- Alguns vídeos do X podem ter restrições
- Verifique se o link está correto

### Erro ao processar matéria
- Nem todos os sites permitem scraping
- Verifique se a matéria tem imagem (og:image)
- Tente com outro site de notícias

## 📝 Exemplos

### Criar 3 posts rapidamente

```
/post_foto https://contigo.com.br/news1
/post_foto https://ofuxico.com.br/news2
/post_video https://gente.ig.com.br/news3 https://x.com/user/status/123 10
```

### Verificar progresso

```
/status
```

Resposta:
```
📊 Status da Fila

📸 Posts com foto: 2
🎥 Posts com vídeo: 1
📦 Total: 3

Os posts serão processados pelo GitHub Actions.
```

## 🔐 Segurança

- Nunca compartilhe seu bot token
- Use secrets do GitHub para tokens sensíveis
- O bot só aceita comandos do `TELEGRAM_CHAT_ID` configurado
- Arquivos de requisição são commitados no repositório (considere adicionar `.gitignore`)

## 🚧 Melhorias Futuras

- [ ] Adicionar overlay de texto nos vídeos do X
- [ ] Suporte para download de vídeos do Instagram/TikTok
- [ ] Fila com prioridade
- [ ] Agendar posts para horários específicos
- [ ] Preview antes de publicar
- [ ] Múltiplos estilos de post
- [ ] Analytics de posts enviados
