# ✅ Checklist de Validação - Sistema Telegram

Use este checklist para validar que tudo está funcionando corretamente.

## 📋 Pré-requisitos

### Bot do Telegram
- [ ] Bot criado no @BotFather
- [ ] Token do bot copiado
- [ ] Chat ID obtido via @userinfobot
- [ ] Enviou `/start` para o bot

### GitHub
- [ ] Secret `TELEGRAM_BOT_TOKEN` configurado
- [ ] Secret `TELEGRAM_CHAT_ID` configurado
- [ ] Secret `OPENAI_API_KEY` configurado (já deve existir)
- [ ] Workflow `.github/workflows/telegram_queue.yml` existe
- [ ] Actions habilitadas no repositório

### Arquivos Locais
- [ ] Diretório `telegram_queue/` existe
- [ ] Script `scripts/telegram_bot.py` existe
- [ ] Script `scripts/process_telegram_queue.py` existe
- [ ] Script `scripts/test_telegram_system.py` existe
- [ ] Workflow file `.github/workflows/telegram_queue.yml` existe

---

## 🧪 Testes Locais

### Teste 1: Criar Requisição de Teste
```bash
cd /Users/caioalbanese/Documents/Tiktok_farm
python scripts/test_telegram_system.py foto
```

**Resultado esperado:**
```
✅ Requisição de teste criada: telegram_queue/request_YYYYMMDD_HHMMSS.json
📋 ID: YYYYMMDD_HHMMSS
📸 Tipo: Post com foto
```

- [ ] Comando executou sem erros
- [ ] Arquivo JSON foi criado em `telegram_queue/`
- [ ] Arquivo contém dados válidos

### Teste 2: Listar Fila
```bash
python scripts/test_telegram_system.py list
```

**Resultado esperado:**
```
📦 1 requisições na fila:

⏳ YYYYMMDD_HHMMSS
   Tipo: foto
   Status: pending
   Criado: 2026-02-14T...
```

- [ ] Lista mostra requisição criada
- [ ] Status está como "pending"
- [ ] Dados estão corretos

### Teste 3: Processar Fila (Opcional - requer dependências)
```bash
python scripts/process_telegram_queue.py
```

**Se funcionar:**
- [ ] Script busca matéria
- [ ] Baixa imagem
- [ ] Renderiza vídeo
- [ ] Tenta enviar para Telegram

**Se falhar:** Normal! Requer ffmpeg, fontes, etc. O GitHub Actions tem tudo.

### Teste 4: Limpar Fila
```bash
python scripts/test_telegram_system.py clear
```

- [ ] Remove requisições completadas/failed

---

## 📱 Testes com Bot Real

### Teste 5: Bot Responde (Opcional - requer bot rodando)
```bash
# Execute o bot localmente
export TELEGRAM_BOT_TOKEN="seu_token"
export TELEGRAM_CHAT_ID="seu_chat_id"
python scripts/telegram_bot.py
```

**No Telegram, envie:**
```
/start
```

**Resultado esperado:**
- [ ] Bot responde com mensagem de ajuda
- [ ] Comandos aparecem corretamente

**Envie:**
```
/help
```

- [ ] Bot lista todos os comandos disponíveis

### Teste 6: Criar Post com Foto (Via Telegram)
**No Telegram:**
```
/post_foto https://contigo.com.br/noticias/novidades/veja-como-esta-o-elenco-de-malhacao-sonhos-anos-depois-do-fim-da-novela
```

**Resultado esperado:**
- [ ] Bot responde confirmando criação
- [ ] Arquivo JSON aparece em `telegram_queue/`
- [ ] Status inicial é "pending"

### Teste 7: Status
**No Telegram:**
```
/status
```

**Resultado esperado:**
- [ ] Bot mostra quantidade de posts na fila
- [ ] Separado por tipo (foto/vídeo)

---

## ⚙️ Testes GitHub Actions

### Teste 8: Disparo Manual
1. Vá em: GitHub → Actions → Process Telegram Queue
2. Clique em "Run workflow"
3. Selecione branch "main"
4. Clique em "Run workflow" (botão verde)

**Aguarde 2-5 minutos**

**Verificações:**
- [ ] Workflow iniciou
- [ ] Checkout concluído
- [ ] Python instalado
- [ ] Dependências instaladas
- [ ] Queue processada (ou mensagem "Nenhuma requisição na fila")

### Teste 9: Verificar Logs
No workflow que executou:
- [ ] Logs mostram "Processando fila de requisições do Telegram..."
- [ ] Se havia requisições: vê tentativa de processamento
- [ ] Se não havia: vê "📭 Nenhuma requisição na fila"
- [ ] Workflow completa sem erros críticos

### Teste 10: Artifacts (Se houve processamento)
- [ ] Artifacts foram criados?
- [ ] Arquivo .mp4 disponível para download?
- [ ] Tamanho razoável (~1-5MB)?

---

## 🎬 Teste End-to-End Completo

Este é o teste final - fluxo completo do sistema.

### Preparação
1. [ ] Secrets configurados no GitHub
2. [ ] Bot funcionando (local ou esperando cron)
3. [ ] Fila limpa (`test_telegram_system.py clear`)

### Execução

**Passo 1: Criar Requisição**

Via bot local:
```bash
python scripts/telegram_bot.py &
```

No Telegram:
```
/post_foto https://ofuxico.com.br/noticias-sobre-famosos/conheca-a-mulher-do-apresentador-tadeu-schmidt.phtml
```

Ou direto na fila:
```bash
python scripts/test_telegram_system.py foto
```

**Passo 2: Disparar Processamento**

Opção A - Manual (mais rápido):
- GitHub → Actions → Process Telegram Queue → Run workflow

Opção B - Automático:
- Aguardar até 15 minutos (cron)

**Passo 3: Acompanhar**
- [ ] Workflow iniciou
- [ ] Encontrou requisição
- [ ] Buscou matéria
- [ ] Baixou imagem
- [ ] Renderizou vídeo
- [ ] Enviou para Telegram ✅

**Passo 4: Validar Resultado**
- [ ] Vídeo recebido no Telegram
- [ ] Formato vertical (9:16)
- [ ] Headline visível
- [ ] Duração ~5 segundos
- [ ] Qualidade boa
- [ ] Caption com link da matéria

**Passo 5: Verificar Estado Final**
```bash
python scripts/test_telegram_system.py list
```

- [ ] Status da requisição mudou para "completed"
- [ ] Timestamp de processamento presente

---

## 🎥 Teste de Vídeo (Avançado)

Se quiser testar posts com vídeo:

**No Telegram:**
```
/post_video https://contigo.com.br/noticias/novidades/bbb https://www.youtube.com/watch?v=dQw4w9WgXcQ 10
```

**Verificações:**
- [ ] Bot aceita comando
- [ ] Valida parâmetros (3 argumentos)
- [ ] Duração entre 5-60 segundos
- [ ] Cria requisição com type="video"

**No GitHub Actions:**
- [ ] yt-dlp instalado
- [ ] Vídeo baixado
- [ ] Cortado na duração especificada
- [ ] Enviado para Telegram

---

## 🐛 Troubleshooting

### ❌ Requisição não é criada
**Verifique:**
```bash
ls -la telegram_queue/
cat telegram_queue/request_*.json | head -20
```

### ❌ GitHub Actions não processa
**Verifique:**
1. Actions estão habilitadas?
2. Secrets configurados corretamente?
3. Workflow file está na branch main?
4. Há requisições pendentes?

### ❌ Bot não responde
**Verifique:**
```bash
# Teste API do Telegram
curl https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe
```

### ❌ Vídeo não é criado
**Verifique logs do Actions:**
- Erro ao buscar matéria? → Site pode bloquear scraping
- Erro ao baixar imagem? → URL pode estar inválida
- Erro ao renderizar? → ffmpeg ou fontes faltando

---

## ✅ Checklist Final

Após completar todos os testes:

- [ ] ✅ Bot do Telegram configurado e responde
- [ ] ✅ Requisições são criadas na fila
- [ ] ✅ GitHub Actions processa fila
- [ ] ✅ Vídeos são gerados corretamente
- [ ] ✅ Vídeos são enviados de volta no Telegram
- [ ] ✅ Status das requisições é atualizado
- [ ] ✅ Sistema funciona end-to-end

---

## 📊 Métricas de Sucesso

Após 1 semana de uso:
- [ ] Taxa de sucesso > 80%
- [ ] Tempo médio de processamento < 5 minutos
- [ ] Nenhum erro crítico nos workflows
- [ ] Fila não acumula requisições antigas

---

## 🎉 Sistema Validado!

Se passou em todos os testes, seu sistema está funcionando perfeitamente!

**Próximos passos:**
1. Use diariamente e monitore
2. Ajuste conforme necessário
3. Considere adicionar webhook para velocidade
4. Explore customizações visuais

**Bom trabalho!** 🚀
