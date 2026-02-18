# 🚀 Sistema de Posts via Telegram - Configuração Avançada

## Opções de Processamento

Você tem 3 opções para processar posts do Telegram:

### 1. ⏰ Cron (Padrão - Já Configurado)
- **Como funciona**: GitHub Actions verifica a fila a cada 15 minutos
- **Vantagens**: Simples, sem custo adicional
- **Desvantagens**: Delay de até 15 minutos
- **Configuração**: Nenhuma adicional necessária

### 2. 🔔 Push-based (Recomendado)
- **Como funciona**: Bot comita requisição → GitHub Actions dispara automaticamente
- **Vantagens**: Processamento em ~1-2 minutos
- **Desvantagens**: Requer configurar bot para fazer push
- **Configuração**: Ver seção "Push-based Setup" abaixo

### 3. ⚡ Webhook (Processamento Imediato)
- **Como funciona**: Telegram envia webhook → Servidor recebe → GitHub Actions dispara
- **Vantagens**: Processamento instantâneo
- **Desvantagens**: Requer servidor web (Railway/Render/Heroku)
- **Configuração**: Ver seção "Webhook Setup" abaixo

---

## Push-based Setup (Opção 2)

Esta opção faz com que o bot comite requisições no GitHub, disparando o workflow automaticamente.

### 1. Crie Personal Access Token (PAT)

1. Vá em GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token (classic)
3. Selecione scopes:
   - `repo` (todos)
   - `workflow`
4. Copie o token

### 2. Configure no Servidor

```bash
export GITHUB_TOKEN="ghp_seu_token_aqui"
export GITHUB_REPOSITORY="seu-usuario/Tiktok_farm"
```

### 3. Crie Bot com Push

Crie `scripts/telegram_bot_push.py`:

```python
#!/usr/bin/env python3
"""Bot que faz push das requisições para o GitHub."""

import json
import subprocess
from pathlib import Path
from datetime import datetime
from scripts.telegram_bot import TelegramBot, QUEUE_DIR, ROOT_DIR

class PushBot(TelegramBot):
    """Bot que faz push automático para o GitHub."""
    
    def handle_post_foto(self, chat_id: str, args: str) -> None:
        super().handle_post_foto(chat_id, args)
        self.push_to_github()
    
    def handle_post_video(self, chat_id: str, args: str) -> None:
        super().handle_post_video(chat_id, args)
        self.push_to_github()
    
    def push_to_github(self):
        """Faz push das requisições para o GitHub."""
        try:
            subprocess.run(["git", "add", "telegram_queue/"], cwd=ROOT_DIR, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"feat: new telegram request {datetime.now().isoformat()}"],
                cwd=ROOT_DIR,
                check=True
            )
            subprocess.run(["git", "push"], cwd=ROOT_DIR, check=True)
            print("✅ Requisição enviada ao GitHub")
        except Exception as e:
            print(f"⚠️ Erro ao fazer push: {e}")

if __name__ == "__main__":
    import os
    bot = PushBot(os.getenv("TELEGRAM_BOT_TOKEN"))
    bot.run_polling()
```

### 4. Execute

```bash
python scripts/telegram_bot_push.py
```

Agora quando você enviar um comando, o bot fará push automaticamente e o GitHub Actions processará em ~1-2 minutos!

---

## Webhook Setup (Opção 3)

Para processamento instantâneo, você pode hospedar um webhook que recebe as atualizações do Telegram.

### 1. Instale Dependências

```bash
pip install flask gunicorn
```

### 2. Deploy no Railway (Grátis)

1. Acesse [railway.app](https://railway.app)
2. Login com GitHub
3. New Project → Deploy from GitHub repo
4. Selecione seu repositório
5. Configure variáveis de ambiente:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GITHUB_TOKEN`
   - `GITHUB_REPOSITORY`

6. Deploy!

### 3. Configure Webhook no Telegram

Após o deploy, você terá uma URL tipo: `https://seu-app.railway.app`

```bash
python scripts/telegram_webhook.py set https://seu-app.railway.app/webhook
```

Verifique:
```bash
python scripts/telegram_webhook.py info
```

### 4. Teste

Envie um comando no Telegram:
```
/post_foto https://contigo.com.br/noticias/sua-materia
```

O processamento deve começar **imediatamente**!

---

## Alternativas de Hosting Gratuito

### Railway
- 500 horas/mês grátis
- Deploy automático do GitHub
- **Recomendado para este projeto**

```bash
# Configuração Railway
railway.toml:
[build]
builder = "nixpacks"

[deploy]
startCommand = "gunicorn -b 0.0.0.0:$PORT 'scripts.telegram_webhook:app'"
```

### Render
- Grátis com limitações (spin down após inatividade)
- Bom para testes

```yaml
# render.yaml
services:
  - type: web
    name: telegram-webhook
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python scripts/telegram_webhook.py server
```

### Fly.io
- Grátis até 3 apps
- Deploy global

```toml
# fly.toml
app = "telegram-webhook"

[http_service]
  internal_port = 8080
  force_https = true

[[services.ports]]
  port = 80
  handlers = ["http"]

[[services.ports]]
  port = 443
  handlers = ["tls", "http"]
```

---

## Teste Local de Webhook

Para testar localmente com ngrok:

### 1. Instale ngrok

```bash
brew install ngrok  # macOS
# ou baixe de https://ngrok.com
```

### 2. Inicie o servidor local

```bash
python scripts/telegram_webhook.py server
```

### 3. Exponha com ngrok

```bash
ngrok http 8080
```

Você verá uma URL tipo: `https://abc123.ngrok.io`

### 4. Configure o webhook

```bash
python scripts/telegram_webhook.py set https://abc123.ngrok.io/webhook
```

### 5. Teste

Envie mensagens no Telegram e veja os logs no terminal!

---

## Monitoramento

### Ver logs do webhook (Railway)

```bash
railway logs
```

### Ver logs do GitHub Actions

1. Vá em Actions no GitHub
2. Selecione "Process Telegram Queue"
3. Veja os logs de execução

### Verificar fila

```bash
python scripts/test_telegram_system.py list
```

---

## Troubleshooting Avançado

### Webhook não recebe atualizações

1. Verifique se está configurado:
   ```bash
   python scripts/telegram_webhook.py info
   ```

2. Teste o endpoint:
   ```bash
   curl https://seu-app.railway.app/health
   ```

3. Veja os logs do servidor

### GitHub Actions não dispara

1. Verifique se o workflow tem permissão:
   ```yaml
   permissions:
     contents: write
     actions: write
   ```

2. Confirme que o token tem scope `workflow`

3. Teste disparo manual:
   ```bash
   curl -X POST \
     -H "Authorization: token $GITHUB_TOKEN" \
     -H "Accept: application/vnd.github.v3+json" \
     https://api.github.com/repos/$GITHUB_REPOSITORY/dispatches \
     -d '{"event_type":"telegram_request"}'
   ```

### Bot não responde

1. Se usando polling, certifique que webhook está deletado:
   ```bash
   python scripts/telegram_webhook.py delete
   ```

2. Verifique tokens e IDs

3. Teste conectividade:
   ```bash
   curl https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe
   ```

---

## Comparação de Opções

| Característica | Cron (15min) | Push-based | Webhook |
|---------------|--------------|------------|---------|
| Delay | ~7-15 min | ~1-2 min | Instantâneo |
| Custo | Grátis | Grátis | Grátis* |
| Complexidade | Baixa | Média | Alta |
| Servidor | Não | Não | Sim |
| Requer Push | Não | Sim | Não |

*Railway: 500h/mês grátis (suficiente para uso pessoal)

---

## Recomendações

**Para uso pessoal/teste**: Use **Cron** (padrão)
- Simples, já funciona
- 15 minutos é aceitável

**Para produção leve**: Use **Push-based**
- Processamento em 1-2 minutos
- Sem custos adicionais
- Requer bot rodando em servidor

**Para produção pesada**: Use **Webhook**
- Processamento instantâneo
- Melhor experiência do usuário
- Requer hospedagem (Railway grátis)

---

## Próximos Passos

1. ✅ Sistema básico funcionando (Cron)
2. 🔄 Implemente Push-based se precisar mais velocidade
3. ⚡ Configure Webhook se precisar processamento instantâneo
4. 📊 Adicione analytics (quantos posts por dia, taxa de sucesso, etc)
5. 🎨 Adicione mais templates de posts
6. 📱 Crie dashboard web para gerenciar fila

---

## Suporte

Para dúvidas ou problemas:
1. Verifique os logs do GitHub Actions
2. Teste com `scripts/test_telegram_system.py`
3. Revise `TELEGRAM_BOT_GUIDE.md` para guia básico
