Guia de Geração de Posts de Fofoca com Vídeo

## 📋 Visão Geral

Este projeto possui duas funcionalidades principais para geração de posts de fofoca:
1. **Posts com imagem estática** - Notícias de feeds RSS com imagem de capa
2. **Posts com vídeo** - Vídeos baixados de redes sociais (Twitter/X, GloboPlay) com overlay de texto

Ambos seguem o mesmo padrão visual de posts verticais 9:16 para TikTok/Reels/Shorts.

---

## 🎨 Padrão Visual dos Posts

### Elementos Comuns (Imagem e Vídeo)
- **Formato**: 1080x1920 (9:16 vertical)
- **Hook**: Texto chamativo no topo com fundo preto semi-transparente (2 linhas max, 20 chars/linha)
- **Headline**: Texto principal na parte inferior (até 7 linhas, 22 chars/linha)
- **Logo**: Animado no topo-centro (escala pulsante com sin wave)
- **CTA**: Texto piscante na parte inferior (ex: "CURTE SE FICOU CHOCADO")
- **Fonte**: BebasNeue-Bold.ttf
- **Cores**: Paleta determinística baseada no hash do texto da headline

### Diferenças entre Imagem e Vídeo
- **Posts com imagem**: 
  - Duração fixa de 5 segundos
  - 3 tarjas transparentes sobre a imagem (para destacar o texto)
  - Áudio sintético (tom senoidal de 247Hz)

- **Posts com vídeo**:
  - Duração variável (cortado conforme necessário, geralmente 15-20s)
  - **SEM tarjas transparentes** (para não cobrir o vídeo)
  - Áudio original do vídeo preservado

---

## 🛠️ Ferramentas e Arquivos

### Scripts Principais

#### 1. `create_gossip_post.py`
**Função**: Gera posts de notícias de feeds RSS com imagem
- Busca notícias em feeds configurados (FEED_PROFILES)
- Baixa imagem da notícia
- Usa IA (OpenAI) para gerar textos otimizados
- Renderiza vídeo vertical com `_render_short()`
- Envia automaticamente para Telegram

**Uso**:
```bash
python3 scripts/create_gossip_post.py --profile br
python3 scripts/create_gossip_post.py --profile intl --logo gossip_post/logo.png
```

#### 2. Scripts de Posts com Vídeo
- `create_bbb_treta_post.py` - Exemplo: "Treta!! Boneco e Edilson brigam no BBB"
- `create_leandro_chora_post.py` - Exemplo: "Choro no BBB! Leandro chora após briga"
- `create_abraco_leandro_post.py` - Exemplo: "Reconciliação! Brothers dão abraço em Leandro"

**Estrutura típica**:
```python
# 1. Baixar vídeo (se necessário)
yt-dlp -f mp4 -o "gossip_post/output/video.mp4" "URL"

# 2. Cortar vídeo (opcional)
ffprobe para obter duração
ffmpeg -ss START -i input.mp4 -t DURATION -c copy output.mp4

# 3. Definir textos
hook_text = "TEXTO CHAMATIVO"
headline_text = "TEXTO PRINCIPAL DA NOTICIA"

# 4. Renderizar com _render_short_video()
_render_short_video(
    video_input,
    headline_file,
    "BBB",
    output_video,
    hook_file=hook_file,
    cta_text="CURTE SE FICOU CHOCADO",
    logo_path=logo_path,
)

# 5. Enviar para Telegram
_send_video_to_telegram(output_video, caption)
```

### Funções Principais

#### `_render_short(image_path, headline_file, source, out_video, ...)`
Renderiza post com **imagem estática**
- **Entrada**: Imagem JPG/PNG
- **Saída**: Vídeo MP4 de 5 segundos
- **Características**: Com tarjas transparentes, áudio sintético

#### `_render_short_video(video_path, headline_file, source, out_video, ...)`
Renderiza post com **vídeo**
- **Entrada**: Vídeo MP4
- **Saída**: Vídeo MP4 com overlay de texto
- **Duração**: Limitado a 20 segundos (ajustável via `-t` no ffmpeg)
- **Características**: SEM tarjas transparentes, áudio original preservado

#### `_send_video_to_telegram(video_path, caption)`
Envia vídeo para o Telegram
- **Bot Token**: `TELEGRAM_BOT_TOKEN` (env ou hardcoded)
- **Chat ID**: `TELEGRAM_CHAT_ID` (env ou hardcoded: 1015015823)
- **Retorno**: True se sucesso, False se falha

---

## 📝 Workflow Típico: Post com Vídeo

### Exemplo Completo: Post do BBB

```bash
# 1. Baixar vídeo do Twitter/X
yt-dlp -f mp4 -o "gossip_post/output/gossip_boneco_edilson_bbb.mp4" \
  "https://x.com/bbb/status/2022540808054878524"

# 2. Criar script Python (ou usar inline)
python3 << 'EOF'
from pathlib import Path
import sys
sys.path.insert(0, "scripts")
from create_gossip_post import _render_short_video, _send_video_to_telegram

# Caminhos
post_dir = Path("gossip_post")
video_input = post_dir / "output" / "gossip_boneco_edilson_bbb.mp4"
output_video = post_dir / "output" / "gossip_bbb_treta_post.mp4"

# Textos
hook_text = "TRETA!!"
headline_text = "BONECO E EDILSON BRIGAM NO BBB"

# Criar arquivos de texto
hook_file = post_dir / "hook_bbb.txt"
headline_file = post_dir / "headline_bbb.txt"
hook_file.write_text(hook_text, encoding="utf-8")
headline_file.write_text(headline_text, encoding="utf-8")

# Logo (opcional)
logo_path = post_dir / "logo.png" if (post_dir / "logo.png").exists() else None

# Renderizar
_render_short_video(
    video_input,
    headline_file,
    "BBB",
    output_video,
    hook_file=hook_file,
    summary_file=headline_file,
    cta_text="CURTE SE FICOU CHOCADO",
    logo_path=logo_path,
)

# Enviar para Telegram
caption = "🔥 TRETA!!\n\nBONECO E EDILSON BRIGAM NO BBB\n\n#BBB #BBB26 #Treta"
_send_video_to_telegram(output_video, caption)
EOF
```

---

## 🎯 Dicas de Textos

### Hook (Texto de Cima)
- **Tamanho**: Máximo 2 linhas, ~20 caracteres por linha
- **Estilo**: TUDO EM CAIXA ALTA, chamativo, urgente
- **Exemplos**:
  - "TRETA!!"
  - "CHORO NO BBB!"
  - "RECONCILIACAO!"
  - "ELIMINADA!"
  - "BARRACO!"

### Headline (Texto Principal)
- **Tamanho**: Até 7 linhas, ~22 caracteres por linha
- **Estilo**: CAIXA ALTA, direto ao ponto
- **Formato**: Sujeito + Verbo + Complemento
- **Exemplos**:
  - "BONECO E EDILSON BRIGAM NO BBB"
  - "LEANDRO CHORA APOS BRIGA COM EDILSON"
  - "BROTHERS DAO ABRACO EM LEANDRO APOS DISCUSSAO"

### CTA (Call-to-Action)
- **Estilo**: CAIXA ALTA, interativo, contextual
- **Exemplos**:
  - "CURTE SE FICOU CHOCADO"
  - "LIKE SE FOI EXAGERO"
  - "CURTE SE FOI LINDO"
  - "LIKE SE MERECIA"
  - "CURTE SE CONCORDA"

---

## 🔧 Configurações Técnicas

### FFmpeg
- **Versão customizada**: `tools/ffmpeg/ffmpeg` (com suporte a drawtext via libfreetype)
- **Fallback**: Sistema `/opt/homebrew/bin/ffmpeg` (pode não ter drawtext)
- **Detecção**: `ensure_ffmpeg("tools")` detecta automaticamente a melhor versão

### Parâmetros de Renderização (Vídeo)
```bash
ffmpeg -hide_banner -y \
  -t 20 \                          # Limita a 20 segundos
  -i input_video.mp4 \
  -vf "scale=1080:1920:...,        # Escala para 9:16
       pad=1080:1920:...,          # Padding com cor de fundo
       eq=brightness=-0.02:...,    # Ajustes de cor
       drawtext=...,               # Hook no topo
       drawtext=...,               # Headline embaixo
       drawtext=..."               # CTA piscante
  -map 0:v:0 -map 0:a:0 \          # Mapeia vídeo e áudio
  -c:v libx264 \
  -c:a aac \
  -b:a 128k \
  -preset medium \
  -crf 20 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  output.mp4
```

### Limitações
- **Tamanho Telegram**: Vídeos >50MB podem dar timeout ao enviar
- **Solução**: Cortar vídeo para 15-20 segundos ou reduzir CRF/bitrate
- **Duração recomendada**: 15-20 segundos para engajamento ideal

---

## 📂 Estrutura de Arquivos

```
gossip_post/
├── output/                          # Vídeos gerados
│   ├── gossip_boneco_edilson_bbb.mp4          # Vídeo baixado original
│   ├── gossip_bbb_treta_post.mp4               # Post renderizado
│   ├── gossip_leandro_chora_bbb.mp4
│   ├── gossip_leandro_chora_post.mp4
│   ├── gossip_abraco_leandro_bbb_full.mp4      # Vídeo completo baixado
│   ├── gossip_abraco_leandro_bbb_15s.mp4       # Vídeo cortado (15s)
│   └── gossip_abraco_leandro_post.mp4          # Post renderizado
├── hook_bbb.txt                     # Texto do hook temporário
├── headline_bbb.txt                 # Texto da headline temporário
├── hook_leandro.txt
├── headline_leandro.txt
├── hook_abraco.txt
├── headline_abraco.txt
├── logo.png                         # Logo opcional para overlay
├── caption.txt                      # Caption para redes sociais
├── news.json                        # Metadata da notícia (posts com RSS)
└── history.json                     # Histórico de posts gerados
```

---

## 🚀 Exemplos de Comandos Rápidos

### Baixar vídeo do Twitter/X
```bash
yt-dlp -f mp4 -o "gossip_post/output/video.mp4" "URL_DO_TWITTER"
```

### Baixar vídeo do GloboPlay
```bash
yt-dlp -f best -o "gossip_post/output/video.mp4" "https://globoplay.globo.com/v/ID"
```

### Cortar últimos 15 segundos de um vídeo
```bash
# Obter duração total
ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 input.mp4

# Cortar (exemplo: vídeo de 88s, pegar 73-88s)
ffmpeg -ss 73 -i input.mp4 -t 15 -c copy output_15s.mp4
```

### Gerar post completo inline
```bash
python3 scripts/create_bbb_treta_post.py
```

### Enviar para Telegram
```bash
python3 scripts/send_bbb_treta_post_telegram.py
```

---

## 🐛 Troubleshooting

### Erro: "No such filter: 'drawtext'"
**Problema**: FFmpeg do sistema não tem suporte a drawtext  
**Solução**: O script detecta automaticamente e usa `tools/ffmpeg/ffmpeg`

### Erro: Timeout ao enviar para Telegram
**Problema**: Vídeo muito grande (>50MB)  
**Solução**: 
- Reduzir duração para 15-20s
- Aumentar CRF (20 → 23)
- Reduzir preset (medium → fast)

### Posts com tarjas transparentes indesejadas
**Problema**: As 3 linhas de drawbox estavam ativas na função `_render_short_video`  
**Solução**: ✅ JÁ CORRIGIDO - Tarjas removidas em 14/02/2026

### Vídeo não chegou no Telegram
**Problema**: Script rodou mas não enviou  
**Solução**: 
- Verificar credenciais: `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`
- Tentar enviar manualmente: `python3 scripts/send_[nome]_telegram.py`
- Verificar conexão de rede

---

## 📊 Histórico de Posts Criados (Exemplos)

| Data | Tema | Hook | Headline | Duração | Status |
|------|------|------|----------|---------|--------|
| 14/02/26 | BBB Treta | TRETA!! | BONECO E EDILSON BRIGAM NO BBB | 20s | ✅ Enviado |
| 14/02/26 | BBB Choro | CHORO NO BBB! | LEANDRO CHORA APOS BRIGA COM EDILSON | 20s | ✅ Enviado |
| 14/02/26 | BBB Reconciliação | RECONCILIACAO! | BROTHERS DAO ABRACO EM LEANDRO APOS DISCUSSAO | 15s | ✅ Enviado |

---

## 🔄 Próximas Melhorias Sugeridas

1. **Script unificado**: Criar um único script que recebe URL + textos e gera tudo
2. **Auto-corte inteligente**: Detectar momentos-chave do vídeo automaticamente
3. **Batch processing**: Processar múltiplos vídeos de uma vez
4. **Legendas automáticas**: Transcrever áudio e adicionar legendas sincronizadas
5. **Análise de sentimento**: Sugerir CTAs baseados no conteúdo do vídeo
6. **Playlist Telegram**: Organizar posts em canal/grupo por categoria

---

## 📞 Contatos e Referências

- **Telegram Bot**: Token configurado em `TELEGRAM_BOT_TOKEN`
- **Chat ID padrão**: 1015015823
- **Feeds RSS**: Configurados em `FEED_PROFILES` (contigo, ofuxico, terra, tmz, pagesix)
- **OpenAI**: Usado para gerar textos otimizados em posts de RSS

---

**Última atualização**: 14 de fevereiro de 2026  
**Versão**: 1.0  
**Autor**: Sistema de geração automática de posts de fofoca
