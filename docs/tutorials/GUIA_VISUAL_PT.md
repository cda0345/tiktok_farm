# 🇧🇷 Sistema de Posts via Telegram - Guia Visual

## 🎯 Como Funciona (Simples)

```
Você envia mensagem → Bot cria requisição → GitHub Actions processa → Vídeo pronto!
```

## 📱 Passo a Passo Rápido

### 1️⃣ Configure o Bot (2 minutos)

**No Telegram:**
1. Fale com [@BotFather](https://t.me/BotFather)
2. Digite `/newbot`
3. Escolha um nome: "Meu Bot de Posts"
4. Copie o TOKEN que ele dá

**No GitHub:**
1. Vá em: Seu Repositório → Settings → Secrets → Actions
2. Adicione:
   - Nome: `TELEGRAM_BOT_TOKEN` | Valor: seu_token_aqui
   - Nome: `TELEGRAM_CHAT_ID` | Valor: seu_id_aqui

💡 **Seu ID:** Fale com [@userinfobot](https://t.me/userinfobot) para descobrir

---

### 2️⃣ Use o Bot

**No Telegram, envie:**

#### 📸 Para criar post com foto:
```
/post_foto https://contigo.com.br/noticias/fulano-se-separa
```

#### 🎥 Para criar post com vídeo:
```
/post_video https://contigo.com.br/treta https://x.com/fulano/status/123 15
```
- Último número = duração em segundos (5 a 60)

#### 📊 Ver status:
```
/status
```

---

### 3️⃣ Aguarde o Processamento

⏰ **Modo Padrão:** A cada 15 minutos o GitHub Actions processa a fila

Você receberá o vídeo de volta no Telegram quando ficar pronto!

---

## 📋 Comandos Disponíveis

| Comando | O que faz | Exemplo |
|---------|-----------|---------|
| `/post_foto <link>` | Cria post com foto da matéria | `/post_foto https://...` |
| `/post_video <materia> <video> <seg>` | Cria post com vídeo do X | `/post_video https://... https://x.com/... 10` |
| `/status` | Mostra quantos posts na fila | `/status` |
| `/help` | Mostra ajuda | `/help` |

---

## 🎨 Exemplos Práticos

### Exemplo 1: Post sobre BBB
```
/post_foto https://gshow.globo.com/realities/bbb/bbb-25/noticia/fulano-briga-com-beltrano.ghtml
```

**Resultado:** Vídeo vertical (9:16) de 5 segundos com:
- Foto da matéria
- Headline em destaque
- Pronto para TikTok/Reels

### Exemplo 2: Post com vídeo de treta
```
/post_video https://ofuxico.com.br/bbb-treta https://x.com/bbboficial/status/1234567 12
```

**Resultado:** Vídeo de 12 segundos com:
- Vídeo baixado do X/Twitter
- Headline da matéria sobreposta
- Cortado na duração que você escolheu

### Exemplo 3: Criar vários posts de uma vez
```
/post_foto https://contigo.com.br/news1
/post_foto https://ofuxico.com.br/news2
/post_video https://gente.ig.com.br/news3 https://x.com/user/status/999 8
/status
```

**Resultado:** 3 posts na fila, todos processados automaticamente!

---

## 🔍 Verificar Progresso

### Ver quantos posts estão na fila:
```
/status
```

**Resposta:**
```
📊 Status da Fila

📸 Posts com foto: 2
🎥 Posts com vídeo: 1
📦 Total: 3

Os posts serão processados pelo GitHub Actions.
```

### Ver logs no GitHub:
1. Vá no seu repositório
2. Clique em "Actions"
3. Selecione "Process Telegram Queue"
4. Veja os logs de execução

---

## ⚡ Quer Mais Velocidade?

### Opção 1: Processar Imediatamente
1. Vá em: Actions → Process Telegram Queue
2. Clique em "Run workflow"
3. Confirme
4. Posts processados em ~2-3 minutos!

### Opção 2: Bot Rodando Localmente
Execute no seu computador:
```bash
./run_telegram_bot.sh
```

Quando você enviar comando, ele já cria a requisição e GitHub Actions processa mais rápido!

### Opção 3: Webhook (Processamento Instantâneo)
Veja `../guides/TELEGRAM_ADVANCED.md` para configurar servidor webhook.

---

## 🐛 Problemas Comuns

### ❌ Bot não responde
**Solução:**
1. Envie `/start` primeiro
2. Verifique se você configurou os secrets corretamente no GitHub
3. Confirme que o token está correto

### ❌ Posts não são criados
**Solução:**
1. Veja os logs em Actions
2. Aguarde até 15 minutos (processamento automático)
3. Ou execute manualmente em Actions → Run workflow

### ❌ Vídeo do X não baixa
**Solução:**
1. Confirme que o link está correto (formato: https://x.com/user/status/123456)
2. Alguns vídeos podem ter restrições
3. Tente com outro vídeo

### ❌ Erro ao buscar matéria
**Solução:**
1. Alguns sites bloqueiam scraping
2. Tente com sites de fofoca brasileiros (Contigo, Ofuxico, Terra Gente, IG Gente)
3. Verifique se o link está correto

---

## 💡 Dicas Pro

### ✅ Melhores Sites para Posts
- ✅ Contigo (https://contigo.com.br)
- ✅ Ofuxico (https://ofuxico.com.br)
- ✅ Terra Gente (https://gente.terra.com.br)
- ✅ IG Gente (https://gente.ig.com.br)
- ✅ GShow BBB (https://gshow.globo.com/realities/bbb)

### ⏱ Melhor Duração para Vídeos
- TikTok: 7-15 segundos
- Reels: 10-15 segundos
- YouTube Shorts: 15-30 segundos

### 📱 Formatos Criados
Todos os vídeos são criados em:
- Formato: 9:16 (vertical)
- Resolução: 1080x1920
- Pronto para TikTok, Reels, Shorts

---

## 📚 Mais Informações

- **Setup Rápido:** `QUICK_START_TELEGRAM.md`
- **Guia Completo:** `../guides/TELEGRAM_BOT_GUIDE.md`
- **Configurações Avançadas:** `../guides/TELEGRAM_ADVANCED.md`
- **Resumo Técnico:** `TELEGRAM_IMPLEMENTATION_SUMMARY.md`
- **Deploy Webhook:** `DEPLOY_CONFIGS.md`

---

## 🎉 Pronto!

Agora você pode criar posts profissionais apenas enviando mensagens no Telegram!

**Comece agora:**
1. Configure os secrets no GitHub (2 minutos)
2. Envie `/post_foto <link>` no Telegram
3. Aguarde o vídeo ficar pronto
4. Publique no TikTok/Reels!

**Bons posts!** 🚀🎬

---

### 🆘 Precisa de Ajuda?

**Teste o sistema:**
```bash
python scripts/test_telegram_system.py foto
python scripts/test_telegram_system.py list
python scripts/process_telegram_queue.py
```

**Verifique a fila:**
```bash
ls -la telegram_queue/
```

**Veja os logs:**
```bash
# No GitHub Actions
Actions → Process Telegram Queue → Logs
```

---

*Criado em 14 de fevereiro de 2026*
*Sistema 100% automatizado e gratuito!* 💚
