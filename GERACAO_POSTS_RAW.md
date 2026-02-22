# GERACAO_POSTS_RAW

Guia para gerar vídeos verticais sem overlay (apenas material bruto), alternando trechos de vídeo e fotos com zoom sutil.

## Objetivo

Criar um `post_raw` com:
- Formato 9:16 (`1080x1920`)
- Sem texto, sem moldura, sem overlay
- Mix de vídeo + fotos de matérias/fontes
- Envio automático para Telegram (opcional)

Script principal:
- `scripts/gerar_post_raw.py`

## Estrutura esperada

Dentro da pasta do post:

```text
posts/<nome_do_post>/
  raw/
    video/
      *.mp4
    images/
      *.jpg|*.jpeg|*.png|*.webp
  output/
```

Exemplo real:
- `posts/2026-02-21_ricky-martin-carnaval/raw/video`
- `posts/2026-02-21_ricky-martin-carnaval/raw/images`

## Como gerar

No diretório `Babado_farm`:

```bash
source .venv/bin/activate
python3 scripts/gerar_post_raw.py \
  --post-dir posts/2026-02-21_ricky-martin-carnaval \
  --name ricky_martin_carnaval_2026_post_raw \
  --duration 11
```

Para já enviar no Telegram:

```bash
python3 scripts/gerar_post_raw.py \
  --post-dir posts/2026-02-21_ricky-martin-carnaval \
  --name ricky_martin_carnaval_2026_post_raw \
  --duration 11 \
  --send-telegram \
  --caption "🎬 RAW MIX sem overlay"
```

## Saídas geradas

Em `posts/<nome_do_post>/output/`:
- `<name>.mp4`: vídeo final sem overlay
- `<name>.json`: manifesto com timeline (segmentos, fontes, duração)

## Regras do pipeline (implementadas)

- Seleciona o vídeo principal automaticamente (maior duração em `raw/video`).
- Seleciona fotos com prioridade de qualidade (evita imagens pequenas que deformam visualmente).
- Intercala vídeo e foto em blocos curtos.
- Foto renderizada com:
  - proporção preservada (foreground central)
  - fundo blur preenchendo 9:16
  - zoom progressivo suave (sem “tremido”)

## Parâmetros principais

- `--post-dir`: pasta do post.
- `--name`: nome base do arquivo de saída.
- `--duration`: duração alvo do vídeo final.
- `--send-telegram`: envia resultado no Telegram.
- `--caption`: legenda usada no Telegram.
- `--seed`: controla variações leves de montagem/zoom.

## Troubleshooting

### 1) Foto “deformada”

Verifique se há imagens muito pequenas em `raw/images` (ex.: thumbnails 800x450).  
O script já prioriza imagens maiores, mas mantenha o diretório com material de boa resolução.

### 2) Foto “tremendo” no zoom

Isso foi resolvido no pipeline atual com zoom progressivo suave + upscale interno + downscale lanczos.  
Se quiser deixar ainda mais estático, reduza o range de `zoom_amount` no script.

### 3) Telegram não envia

Conferir no `.env`:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Exemplo validado

Caso Ricky Martin:
- Entrada: `posts/2026-02-21_ricky-martin-carnaval/raw/...`
- Saída testada: `posts/2026-02-21_ricky-martin-carnaval/output/ricky_martin_carnaval_2026_post_raw_v3.mp4`

## Exemplo validado 2

Caso Carla Perez (encerramento do Carnaval):
- Tema: cantora emocionada na despedida
- Linha criativa: "ELA SE EMOCIONOU..." / "CLIMA PESADO NO FINAL"
- Diretriz: corte direto no momento (sem intercalar foto)
- Entrada: `posts/2026-02-21-carla-perez-encerramento-carnaval/raw/...`
- Saida testada: `posts/2026-02-21-carla-perez-encerramento-carnaval/output/carla_perez_encerramento_carnaval_2026_post_raw.mp4`
