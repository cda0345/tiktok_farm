# Validação (últimos 5 testes) — 2026-02-16

Objetivo: checar consistência do corpo (não cortar no meio), e CTA sem “quadradinho com X”.

## Mudanças aplicadas
- Corpo (`headline_text_clean`) agora é truncado por limite **e respeita fim de frase** via `_truncate_at_sentence_boundary(..., max_chars=220)`.
- CTA passa por `_sanitize_cta_text()` para remover emojis/símbolos que costumam virar tofu no FFmpeg `drawtext`.

## Amostra de saída (último post gerado)

### `gossip_post/headline.txt`
```
HUCK MANDOU UM FELIZ
ANIVERSÁRIO PARA JOJO AO
VIVO. A WEB REAGIU COM
SURPRESA, ELOGIANDO A
ATITUDE DO APRESENTADOR. A
REPERCUSSÃO FORTALECEU A
RELAÇÃO PÚBLICA ENTRE OS
DOIS.
```

### `gossip_post/caption.txt`
```
LUCIANO HUCK SURPREENDE JOJO TODYNHO COM RECADO NO DOMINGÃO
HUCK MANDOU UM FELIZ ANIVERSÁRIO PARA JOJO AO VIVO. A WEB REAGIU COM SURPRESA, ELOGIANDO A ATITUDE DO APRESENTADOR. A REPERCUSSÃO FORTALECEU A RELAÇÃO PÚBLICA ENTRE OS DOIS.

Fonte: CONTIGO
Link: https://contigo.com.br/noticias/tv/luciano-huck-surpreende-com-recado-para-jojo-todynho-no-domingao.phtml
```

## Resultado esperado
- Corpo termina com pontuação (`.`, `?`, `!`) e sem quebra no meio da frase.
- CTA exibido sem tofu (sem glyph desconhecido na frente).
