# Post Pack - Carla Perez Encerramento Carnaval 2026

## Estrutura
- `raw/video/`: recorte bruto ja focado no momento emocional
- `raw/pages/`: HTML da materia + imagens de referencia
- `raw/images/`: vazio por intencao para manter corte direto sem intercalar fotos
- `output/`: video raw final + manifesto json + check sheet

## Tema recente escolhido
- Carla Perez se emociona na despedida do Carnaval de Salvador 2026 (materia publicada em 15/02/2026)

## Linha de criativo (raw)
- "Cantora chorando no encerramento do Carnaval"
- "ELA SE EMOCIONOU..."
- "CLIMA PESADO NO FINAL"
- Corte direto no momento

## Render executado
```bash
python3 scripts/gerar_post_raw.py \
  --post-dir posts/2026-02-21-carla-perez-encerramento-carnaval \
  --name carla_perez_encerramento_carnaval_2026_post_raw \
  --duration 11
```

## Saidas
- `output/carla_perez_encerramento_carnaval_2026_post_raw.mp4`
- `output/carla_perez_encerramento_carnaval_2026_post_raw.json`
- `output/check_sheet_raw.jpg`
