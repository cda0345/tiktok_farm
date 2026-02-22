# Post Pack - Ricky Martin Carnaval 2026

## Estrutura
- `raw/video/`: vídeos brutos
- `raw/images/`: imagens de apoio (OG + contexto)
- `raw/pages/`: páginas fonte salvas localmente
- `output/`: post renderizado + textos de overlay

## Fontes usadas
- Gshow vídeo principal (baixado com sucesso)
- Gshow matéria principal (HTML salvo + imagem OG)
- Gshow Sapucaí/famosos (HTML salvo + imagem OG)
- Caras contexto internacional (site bloqueou `403` no curl direto; conteúdo capturado via `r.jina.ai` em txt e imagens extraídas)

## Artefatos principais
- Raw principal: `raw/video/ricky_martin_globo_raw.mp4`
- Post final: `output/ricky_martin_carnaval_2026_post.mp4`
- Metadados do post: `output/ricky_martin_carnaval_2026_post.json`

## Copy usada no render teste
- Hook: `RICKY MARTIN VIROU CARIOCA?`
- Headline: `RICKY NO CARNAVAL`
- Tarja/body: `PRAIA BIKE E SAPUCAI.`

## Observação
O render foi feito no pipeline atual do projeto (11s), sem áudio original no arquivo final de post.
