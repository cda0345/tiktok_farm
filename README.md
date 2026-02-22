# Babado_farm

Pacote mínimo e autossuficiente para:
- Rodar o scheduler de posts de gossip (`scripts/scheduler.py`)
- Gerar post a partir de link enviado no Telegram (`poll + queue processor`)

## Estrutura
- `scripts/`: fluxo principal (scheduler, polling, processamento da fila, geração de post)
- `core/`: cliente AI e utilitários FFmpeg
- `assets/fonts/`: fontes usadas no overlay
- `gossip_post/`: saída, histórico e artefatos dos posts
- `telegram_queue/`: fila de requisições vindas do Telegram

## Requisitos
- Python 3.11+
- `ffmpeg` e `ffprobe` (ou download automático pelo script)
- `yt-dlp` (instalado via `requirements.txt`)

## Setup
```bash
cd Babado_farm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Preencha no `.env`:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `OPENAI_API_KEY` (opcional)

## Uso

### 1) Scheduler de gossip (3 horários fixos: 12h, 18h, 21h)
```bash
python3 scripts/scheduler.py
```

### 2) Geração por link via Telegram
Terminal A (captura links enviados ao bot e coloca na fila):
```bash
python3 scripts/poll_telegram_to_queue.py
```

Terminal B (processa fila e gera/envia posts):
```bash
python3 scripts/process_telegram_queue_v2.py
```

### 3) Geração RAW (sem overlay) com mix de vídeo + fotos
Usa arquivos já salvos em uma pasta de post (`raw/video` e `raw/images`), intercala trechos e envia para Telegram:
```bash
python3 scripts/gerar_post_raw.py \
  --post-dir posts/2026-02-21_ricky-martin-carnaval \
  --name ricky_martin_carnaval_2026_post_raw \
  --duration 11 \
  --send-telegram
```

## Observações
- O polling aceita links `x.com` e `twitter.com`.
- O processamento de vídeo usa `yt-dlp` + FFmpeg para renderizar e enviar no Telegram.
- Para rodar continuamente, execute os comandos em loop no seu orquestrador preferido (cron, systemd, Actions, etc.).
