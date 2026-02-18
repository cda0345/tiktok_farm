# Configurações de Deploy para Webhook Server

Este diretório contém exemplos de configuração para hospedar o webhook server em diferentes plataformas.

## Railway

1. Crie conta em [railway.app](https://railway.app)
2. New Project → Deploy from GitHub repo
3. Configure variáveis:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GITHUB_TOKEN`
   - `GITHUB_REPOSITORY`
4. Railway detectará automaticamente o `Procfile`

## Render

1. Crie `render.yaml` (exemplo abaixo)
2. Push para GitHub
3. Conecte repositório no [render.com](https://render.com)

```yaml
services:
  - type: web
    name: telegram-webhook
    env: python
    buildCommand: pip install -r requirements.txt -r requirements-webhook.txt
    startCommand: gunicorn -b 0.0.0.0:$PORT 'scripts.telegram_webhook:app'
    envVars:
      - key: TELEGRAM_BOT_TOKEN
        sync: false
      - key: TELEGRAM_CHAT_ID
        sync: false
      - key: GITHUB_TOKEN
        sync: false
      - key: GITHUB_REPOSITORY
        sync: false
```

## Fly.io

1. Instale flyctl: `brew install flyctl`
2. Login: `flyctl auth login`
3. Crie `fly.toml` (exemplo abaixo)
4. Deploy: `flyctl deploy`

```toml
app = "telegram-webhook-tiktok"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0

[[services]]
  protocol = "tcp"
  internal_port = 8080

  [[services.ports]]
    port = 80
    handlers = ["http"]

  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]
```

Configurar secrets:
```bash
flyctl secrets set TELEGRAM_BOT_TOKEN=xxx
flyctl secrets set TELEGRAM_CHAT_ID=xxx
flyctl secrets set GITHUB_TOKEN=xxx
flyctl secrets set GITHUB_REPOSITORY=xxx
```

## Docker (Auto-hospedagem)

1. Crie `Dockerfile` (exemplo abaixo)
2. Build: `docker build -t telegram-webhook .`
3. Run: `docker run -p 8080:8080 -e TELEGRAM_BOT_TOKEN=xxx telegram-webhook`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements-webhook.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-webhook.txt

COPY . .

EXPOSE 8080

CMD ["python", "scripts/telegram_webhook.py", "server"]
```

## Heroku

1. Instale Heroku CLI
2. Login: `heroku login`
3. Crie app: `heroku create telegram-webhook-tiktok`
4. Configure secrets:
   ```bash
   heroku config:set TELEGRAM_BOT_TOKEN=xxx
   heroku config:set TELEGRAM_CHAT_ID=xxx
   heroku config:set GITHUB_TOKEN=xxx
   heroku config:set GITHUB_REPOSITORY=xxx
   ```
5. Deploy: `git push heroku main`

O `Procfile` já está configurado!

## Vercel (Não Recomendado)

⚠️ Vercel é otimizado para serverless/edge functions, não para long-running bots.
Prefira Railway ou Render para este caso.

## Comparação de Plataformas

| Plataforma | Grátis | Deploy | Facilidade | Uptime |
|-----------|--------|--------|------------|--------|
| Railway | 500h/mês | Auto | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Render | Sim (sleep) | Auto | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Fly.io | 3 apps | Manual | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Heroku | Não* | Manual | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Docker | Depende | Manual | ⭐⭐ | Você gerencia |

*Heroku removeu plano gratuito em 2022

## Recomendação

**🏆 Railway** - Melhor opção para começar:
- 500 horas/mês grátis (suficiente para uso 24/7)
- Deploy automático do GitHub
- Interface simples
- Logs em tempo real

## Teste Local Antes de Deployar

```bash
# Instale dependências
pip install -r requirements-webhook.txt

# Execute localmente
python scripts/telegram_webhook.py server

# Em outro terminal, teste com ngrok
ngrok http 8080

# Configure webhook temporário
python scripts/telegram_webhook.py set https://xxx.ngrok.io/webhook

# Teste enviando mensagem no Telegram

# Remova webhook quando terminar
python scripts/telegram_webhook.py delete
```

## Troubleshooting

### Webhook não recebe atualizações

1. Verifique se o servidor está rodando
2. Teste o health endpoint: `curl https://seu-app/health`
3. Veja os logs da plataforma
4. Confirme que o webhook está configurado: `python scripts/telegram_webhook.py info`

### Servidor para após algum tempo

- **Render**: Plano gratuito faz "spin down" após 15min de inatividade
  - Solução: Upgrade para plano pago ou use Railway
- **Fly.io**: Configuração `auto_stop_machines` pode desligar
  - Solução: Ajuste `min_machines_running = 1`

### Erro de permissão no GitHub Actions

- Verifique se o `GITHUB_TOKEN` tem scope `workflow`
- Confirme que o workflow tem `permissions: contents: write`

## Monitoramento

### Uptime Monitoring (Grátis)

Use [UptimeRobot](https://uptimerobot.com) para monitorar:
- URL: `https://seu-app/health`
- Intervalo: 5 minutos
- Alerta: Email/SMS se ficar offline

### Logs

**Railway:**
```bash
railway logs
```

**Render:**
Via dashboard web

**Fly.io:**
```bash
flyctl logs
```

**Docker:**
```bash
docker logs -f container_id
```
