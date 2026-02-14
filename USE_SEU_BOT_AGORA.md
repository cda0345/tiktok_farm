# 🚀 USE SEU BOT AGORA - Guia Rápido

## ✅ Seu bot já está configurado!

**Token:** `8519683231:AAH1RsrgaYmo3v99hd_yfktgoFWHU2AWrP0`
**Chat ID:** `1015015823`

## 📱 Opção 1: Usar Via Telegram (Recomendado)

### Passo 1: Encontre seu bot no Telegram

1. Abra o Telegram
2. Busque por: **@seu_bot** (ou o nome que você deu)
3. Se não lembra, use este link direto:
   ```
   https://t.me/bot8519683231
   ```

### Passo 2: Envie /start

```
/start
```

O bot deve responder se estiver rodando!

### Passo 3: Teste com um comando

```
/post_foto https://contigo.com.br/noticias/novidades/veja-como-esta-o-elenco-de-malhacao-sonhos-anos-depois-do-fim-da-novela
```

**Se o bot NÃO responder:** Prossiga para a Opção 2 (executar bot localmente)

---

## 💻 Opção 2: Executar Bot Localmente

O bot precisa estar rodando para receber mensagens. Execute:

```bash
cd /Users/caioalbanese/Documents/Tiktok_farm
python scripts/telegram_bot.py
```

**Você verá:**
```
🤖 Bot iniciado. Aguardando mensagens...
📁 Fila em: /Users/caioalbanese/Documents/Tiktok_farm/telegram_queue
```

**Agora no Telegram:**
1. Envie `/start` para seu bot
2. Envie `/post_foto https://contigo.com.br/noticias/sua-materia`
3. O bot confirma a criação da requisição!

**Mantenha o terminal aberto** enquanto quiser que o bot responda.

---

## ⚙️ Opção 3: Usar Sem Bot (Direto na Fila)

Se não quiser executar o bot, você pode criar requisições diretamente:

```bash
# Criar requisição de teste
python scripts/test_telegram_system.py foto

# Ver o que foi criado
python scripts/test_telegram_system.py list
```

Depois processe:

### Localmente (se tiver ffmpeg e dependências):
```bash
python scripts/process_telegram_queue.py
```

### Ou via GitHub Actions:
1. Vá em: **Actions → Process Telegram Queue**
2. Clique em **"Run workflow"**
3. Aguarde 2-3 minutos
4. Vídeo será enviado para o Telegram!

---

## 🎬 Teste Completo Rápido

Execute este teste de ponta a ponta:

```bash
# 1. Criar requisição de teste
cd /Users/caioalbanese/Documents/Tiktok_farm
python scripts/test_telegram_system.py foto

# 2. Verificar que foi criada
python scripts/test_telegram_system.py list

# 3. (OPCIONAL) Processar localmente
python scripts/process_telegram_queue.py
```

**Ou processar no GitHub:**
- Actions → Process Telegram Queue → Run workflow

---

## 🔍 Verificar se o Bot Está Funcionando

```bash
# Testar API do Telegram
curl "https://api.telegram.org/bot8519683231:AAH1RsrgaYmo3v99hd_yfktgoFWHU2AWrP0/getMe"
```

**Resposta esperada:**
```json
{
  "ok": true,
  "result": {
    "id": 8519683231,
    "is_bot": true,
    "first_name": "Seu Bot",
    ...
  }
}
```

Se retornou `"ok": true` → Bot está funcionando! ✅

---

## 📝 Comandos do Bot

**No Telegram, você pode enviar:**

### Criar post com foto:
```
/post_foto https://contigo.com.br/noticias/sua-materia
```

### Criar post com vídeo do X:
```
/post_video https://ofuxico.com.br/news https://x.com/fulano/status/123456 15
```
(15 = duração em segundos)

### Ver status da fila:
```
/status
```

### Ver ajuda:
```
/help
```

---

## ⚡ Processamento

### Modo 1: Automático (Padrão)
- GitHub Actions processa a cada 15 minutos
- Você não precisa fazer nada!
- Receberá o vídeo no Telegram quando ficar pronto

### Modo 2: Manual (Mais Rápido)
1. Vá em: **GitHub → Actions → Process Telegram Queue**
2. Clique em **"Run workflow"**
3. Vídeo pronto em ~2-3 minutos

### Modo 3: Local (Debug)
```bash
python scripts/process_telegram_queue.py
```

---

## 🎯 Fluxo Recomendado

### Para uso regular:

1. **Execute o bot localmente** (deixe rodando em background):
   ```bash
   cd /Users/caioalbanese/Documents/Tiktok_farm
   python scripts/telegram_bot.py &
   ```

2. **No Telegram, envie comandos:**
   ```
   /post_foto https://contigo.com.br/noticias/sua-materia
   ```

3. **GitHub Actions processa automaticamente** (a cada 15 min)
   - Ou execute manualmente para processar imediatamente

4. **Receba o vídeo pronto no Telegram!** 🎉

---

## 🐛 Troubleshooting

### Bot não responde no Telegram
```bash
# 1. Verificar se está rodando
ps aux | grep telegram_bot

# 2. Se não está, execute
python scripts/telegram_bot.py
```

### Requisição não é criada
```bash
# Verificar diretório
ls -la telegram_queue/

# Criar teste
python scripts/test_telegram_system.py foto
```

### Vídeo não é gerado
```bash
# Ver logs
python scripts/process_telegram_queue.py

# Ou no GitHub Actions
# Actions → Process Telegram Queue → Ver logs
```

---

## 📊 Verificar GitHub Actions

Os secrets já devem estar configurados (ou use os valores padrão):
- `TELEGRAM_BOT_TOKEN` → 8519683231:AAH1RsrgaYmo3v99hd_yfktgoFWHU2AWrP0
- `TELEGRAM_CHAT_ID` → 1015015823

Para adicionar no GitHub:
1. Settings → Secrets and variables → Actions
2. New repository secret
3. Adicione os valores acima

---

## 🎉 Comece Agora!

**Teste em 30 segundos:**

```bash
# Terminal 1 - Execute o bot
python scripts/telegram_bot.py

# Telegram - Envie mensagem
/post_foto https://contigo.com.br/noticias/novidades/veja-como-esta-o-elenco-de-malhacao-sonhos-anos-depois-do-fim-da-novela

# GitHub - Processe (ou aguarde 15 min)
Actions → Process Telegram Queue → Run workflow
```

**Pronto!** Seu sistema está funcionando! 🚀

---

## 📚 Mais Informações

- **Guia Visual:** `GUIA_VISUAL_PT.md`
- **Guia Completo:** `TELEGRAM_BOT_GUIDE.md`
- **Testes:** `VALIDATION_CHECKLIST.md`

**Bons posts!** 🎬
