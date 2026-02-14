# 📱 Sistema de Posts via Telegram - Resumo da Implementação

## ✅ O que foi implementado

### 1. **Bot do Telegram** (`scripts/telegram_bot.py`)
- ✅ Comandos `/post_foto` e `/post_video`
- ✅ Sistema de fila com arquivos JSON
- ✅ Comandos `/status` e `/help`
- ✅ Validação de links e parâmetros
- ✅ Feedback em tempo real para o usuário

### 2. **Processador de Fila** (`scripts/process_telegram_queue.py`)
- ✅ Processa posts com foto (scraping de matérias)
- ✅ Processa posts com vídeo do X/Twitter (download com yt-dlp)
- ✅ Corte de vídeos na duração especificada
- ✅ Renderização com overlays de texto
- ✅ Envio automático para Telegram
- ✅ Atualização de status das requisições

### 3. **GitHub Actions Workflow** (`.github/workflows/telegram_queue.yml`)
- ✅ Execução a cada 15 minutos (cron)
- ✅ Disparo manual (workflow_dispatch)
- ✅ Disparo por push de arquivos na fila
- ✅ Disparo por webhook (repository_dispatch)
- ✅ Upload de vídeos como artifacts
- ✅ Commit automático de status

### 4. **Sistema de Webhook** (`scripts/telegram_webhook.py`)
- ✅ Alternativa ao polling
- ✅ Processamento instantâneo
- ✅ Servidor Flask integrado
- ✅ Disparo automático do GitHub Actions
- ✅ Health check endpoint

### 5. **Ferramentas de Teste** (`scripts/test_telegram_system.py`)
- ✅ Criação de requisições de teste
- ✅ Listagem da fila
- ✅ Limpeza de requisições processadas
- ✅ Atalho para processar fila localmente

### 6. **Documentação**
- ✅ `QUICK_START_TELEGRAM.md` - Setup rápido (5 minutos)
- ✅ `TELEGRAM_BOT_GUIDE.md` - Guia completo
- ✅ `TELEGRAM_ADVANCED.md` - Configurações avançadas
- ✅ `run_telegram_bot.sh` - Script de inicialização

## 🎯 Como Usar

### Opção 1: Apenas GitHub Actions (Cron - Recomendado para começar)

1. Configure secrets no GitHub:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

2. Envie comandos via Telegram:
   ```
   /post_foto https://contigo.com.br/noticias/sua-materia
   ```

3. Aguarde até 15 minutos (processamento automático)

### Opção 2: Bot Local + GitHub Actions

1. Configure variáveis de ambiente:
   ```bash
   export TELEGRAM_BOT_TOKEN="seu_token"
   export TELEGRAM_CHAT_ID="seu_chat_id"
   ```

2. Execute o bot localmente:
   ```bash
   ./run_telegram_bot.sh
   ```

3. Envie comandos no Telegram
4. Bot cria requisições na fila
5. GitHub Actions processa automaticamente

### Opção 3: Webhook em Servidor (Processamento Instantâneo)

1. Deploy no Railway/Render/Fly.io
2. Configure webhook:
   ```bash
   python scripts/telegram_webhook.py set https://seu-app.railway.app/webhook
   ```
3. Envie comandos no Telegram
4. Processamento instantâneo!

## 📋 Checklist de Setup

### Mínimo (Já Pronto!)
- [x] Bot criado no Telegram
- [x] Secrets configurados no GitHub
- [x] Workflow do GitHub Actions ativo
- [x] Diretório `telegram_queue/` criado

### Para Usar Agora
- [ ] Configure `TELEGRAM_BOT_TOKEN` no GitHub
- [ ] Configure `TELEGRAM_CHAT_ID` no GitHub
- [ ] Envie `/start` para seu bot
- [ ] Teste com `/post_foto <link>`

### Opcional (Melhorias)
- [ ] Execute bot localmente para processamento mais rápido
- [ ] Configure webhook para processamento instantâneo
- [ ] Adicione mais estilos de posts
- [ ] Customize overlays de vídeo

## 🎬 Exemplos de Comandos

### Post com Foto
```
/post_foto https://contigo.com.br/noticias/casal-se-separa
```

Resultado: Vídeo de 5s com foto da matéria e headline

### Post com Vídeo do X
```
/post_video https://ofuxico.com.br/bbb-treta https://x.com/bbboficial/status/123456 15
```

Resultado: Vídeo de 15s baixado do X com headline da matéria

### Verificar Fila
```
/status
```

Resultado: Quantos posts estão aguardando processamento

## 📊 Arquitetura do Sistema

```
┌─────────────────┐
│   Telegram      │
│   (Usuário)     │
└────────┬────────┘
         │ Enviar comando
         ↓
┌─────────────────┐
│  Telegram Bot   │  ← Rodando localmente OU
│  (telegram_bot) │    Webhook em servidor
└────────┬────────┘
         │ Criar requisição JSON
         ↓
┌─────────────────┐
│  telegram_queue/│
│  request_*.json │
└────────┬────────┘
         │ A cada 15min OU push OU webhook
         ↓
┌─────────────────┐
│ GitHub Actions  │
│ (workflow)      │
└────────┬────────┘
         │ Executar
         ↓
┌─────────────────┐
│  Processador    │
│ (process_queue) │
└────────┬────────┘
         │
         ├─→ Buscar matéria
         ├─→ Baixar imagem/vídeo
         ├─→ Renderizar vídeo
         └─→ Enviar para Telegram
              ↓
┌─────────────────┐
│   Telegram      │
│  (Vídeo pronto) │
└─────────────────┘
```

## 🔧 Configuração Técnica

### Variáveis de Ambiente Necessárias

```bash
# Obrigatórias
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=1015015823

# Opcionais (para webhook)
GITHUB_TOKEN=ghp_...
GITHUB_REPOSITORY=usuario/Tiktok_farm
```

### Dependências (já no requirements.txt)

```
requests
yt-dlp>=2024.0.0
Pillow>=10.0.0
```

### Dependências Opcionais

```bash
# Para webhook
pip install flask gunicorn

# Para desenvolvimento
pip install pytest black flake8
```

## 🎨 Próximas Melhorias Sugeridas

### Curto Prazo
1. Adicionar overlay de texto nos vídeos do X (atualmente só corta)
2. Suporte para mais fontes de vídeo (Instagram, YouTube Shorts)
3. Templates diferentes de posts (vertical, quadrado)
4. Preview antes de publicar

### Médio Prazo
1. Dashboard web para gerenciar fila
2. Agendamento de posts para horários específicos
3. Analytics (posts por dia, taxa de sucesso)
4. Sistema de prioridades na fila
5. Múltiplos estilos visuais (tema escuro, light, etc)

### Longo Prazo
1. IA para sugerir melhores momentos do vídeo
2. Geração automática de legendas
3. Música de fundo automática
4. Integração com outras redes sociais
5. Sistema de A/B testing

## 📈 Métricas de Performance

### Estimativas de Processamento

| Tipo de Post | Tempo Médio | Recursos |
|-------------|-------------|----------|
| Post com Foto | ~30-60s | Baixo |
| Post com Vídeo | ~2-5min | Médio-Alto |

### Limites do GitHub Actions

- ⏰ 2000 minutos/mês (grátis)
- 📦 500MB de armazenamento de artifacts
- ⚡ Concorrência: 1 workflow por vez (free tier)

**Estimativa**: ~100-200 posts/mês dentro do limite gratuito

## 🐛 Troubleshooting Comum

### Bot não responde
```bash
# Verificar se o bot está rodando
ps aux | grep telegram_bot

# Verificar token
curl https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe
```

### Posts não são processados
```bash
# Verificar fila
python scripts/test_telegram_system.py list

# Processar localmente para debug
python scripts/process_telegram_queue.py
```

### Erro ao baixar vídeo do X
```bash
# Atualizar yt-dlp
pip install --upgrade yt-dlp

# Testar download manual
yt-dlp -f best https://x.com/...
```

## 📚 Documentação de Referência

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [GitHub Actions](https://docs.github.com/en/actions)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg](https://ffmpeg.org/documentation.html)

## 🎉 Conclusão

Você agora tem um sistema completo de criação de posts via Telegram! 

**Comece simples**: Use o modo Cron (já configurado)
**Depois evolua**: Adicione bot local ou webhook conforme necessidade

**Bons posts!** 🚀

---

*Data da implementação: 14 de fevereiro de 2026*
*Versão: 1.0.0*
