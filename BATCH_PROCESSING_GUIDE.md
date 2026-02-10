# Batch Processing Guide - Gerador de Posts para Instagram/TikTok

## 📋 Visão Geral

Sistema automatizado para gerar posts de vídeo (5-9 segundos) com:
- Download automático de áudio do YouTube (track da música)
- Download automático de b-roll do YouTube (vídeos temáticos)
- **Download automático de Lyrics (LRC)**: Busca sincronizada via LRCLIB, Lyricsify e Megalobiz.
- **Análise de BPM e sinc rítmica complexa** (cortes rítmicos)
- **Engine de Loop Infinito** (transição visual invisível entre o fim e o início)
- **Safe Area TikTok (9:16)**: Margens 10% lateral, 15% inferior, 8-10% superior.
- **Timing de Texto**: Hooks de 3-6 palavras aparecendo nos primeiros 0.5s.
- Renderização com GPU (h264_nvenc) usando 2-pass architecture
- 3 variantes por post com durações aleatórias (5-9s)
- Performance: 19.9-36x real-time speed (1800x mais rápido que versão original)

## 🎯 Performance

- **Velocidade de renderização**: 19.9-36x real-time (0.2-0.3s por segundo de vídeo)
- **Tempo por post**: ~1-2 minutos (3 variantes de 8-10s cada)
- **Batch de 5 posts**: ~5-10 minutos
- **GPU**: NVIDIA h264_nvenc (preset p1 - fastest)
- **CPU**: ThreadPoolExecutor com 4 workers para renderização paralela de segmentos

## 📁 Estrutura do Projeto

```
projeto_insta_pc/
├── main.py                    # Entry point principal
├── online_pipeline.py         # Orquestração do workflow YouTube
├── exporter_fast.py          # Renderizador 2-pass (PRODUÇÃO)
├── batch_posts.py            # Processador de fila de posts
├── posts_queue.csv           # Fila de posts a processar
├── config.py                 # Configurações de renderização
├── providers/
│   └── youtube.py           # Download de áudio/vídeo do YouTube
├── posts/                   # Output: posts gerados
│   ├── post_001_track_name/
│   │   ├── caption.txt
│   │   └── output/
│   │       ├── v1.mp4
│   │       ├── v2.mp4
│   │       └── v3.mp4
│   └── post_XXX_track_name/
├── audio/
│   └── tracks/              # Cache de áudios baixados
└── broll_library/           # Cache de vídeos de b-roll
    ├── style_name_1/
    └── style_name_2/
```

## 🚀 Uso do Batch Processing

### Método 1: Batch Automático (Recomendado)

1. **Edite o arquivo `posts_queue.csv`:**

```csv
post_num,track_name,artist,broll_idea,themes,min_videos
13,Your Love,Frankie Knuckles,DJ booth POV equalizer,dj booth nightlife,6
14,Be Good To Me,Cloonee,nightclub crowd kick,nightlife crowd party,6
15,Can You Feel It,Mr. Fingers,vinyl record spinning turntable,dj vinyl closeup,6
```

2. **Execute o batch processor:**

```powershell
python batch_posts.py posts_queue.csv
```

**O script irá:**
- Processar cada post sequencialmente (foreground)
- Mostrar progresso em tempo real
- Continuar processando mesmo se um post falhar
- Gerar relatório final com sucessos/falhas

### Método 2: Post Individual

```powershell
python main.py --online `
  --online-provider youtube `
  --online-track-id "Artist Track Name" `
  --online-broll-style "search query for b-roll" `
  --online-themes "theme1 theme2 theme3" `
  --online-broll-min-videos 6 `
  --online-post-name "post_013_track_name" `
  --overwrite
```

## 📊 Formato do CSV (posts_queue.csv)

### Campos Obrigatórios

| Campo | Descrição | Exemplo |
|-------|-----------|---------|
| `post_num` | Número do post (3 dígitos) | `13` |
| `track_name` | Nome da música | `Your Love` |
| `artist` | Nome do artista | `Frankie Knuckles` |
| `broll_idea` | Query de busca para b-roll no YouTube | `DJ booth POV equalizer` |
| `themes` | Temas separados por espaço | `dj booth nightlife` |
| `min_videos` | Quantidade mínima de vídeos de b-roll | `6` |

## 🎤 Letras Sincronizadas (Lyrics)

O sistema agora baixa automaticamente o arquivo `lyrics.lrc` para cada post:

### Como funciona:
1. **Identificação**: Usa o `track_id` (combinando artista e música).
2. **Fontes**: 
   - **LRCLIB (Primária)**: API dedicada a letras sincronizadas.
   - **Lyricsify (Secundária)**: Web scraping via Playwright.
   - **Megalobiz (Fallback)**: Web scraping via Playwright se nada for encontrado.
3. **Localização**: O arquivo é salvo como `lyrics.lrc` dentro da pasta do post (ex: `posts/post_013_your_love/lyrics.lrc`).

### Scripts Relacionados:
- `fetch_lyrics.py`: O módulo central que gerencia as buscas. Pode ser rodado manualmente para baixar letras de todos os posts existentes:
  ```powershell
  python fetch_lyrics.py
  ```

## 🎵 Modo "TikTok Lyrics" (Novo)

Crie vídeos de até 10 segundos focados em trechos específicos (refrão), com as letras aparecendo sincronizadas na tela.

### Como usar:
```powershell
python tiktok_lyrics.py --post post_304_ibiza_stussy --start 45 --duration 10
```

**Parâmetros:**
- `--post`: Nome da pasta do post (ex: `post_304_ibiza_stussy`).
- `--start`: Tempo inicial no áudio em segundos (ex: `45`).
- `--duration`: Duração do clip (default `10`).

**Destaques:**
- **Sincronia Rítmica**: O ponto de início é automaticamente ajustado para o beat mais próximo.
- **Visual City-Style**: Mesma fonte Bahnschrift e estética premium dos posts de cidades.
- **Cortes de B-Roll**: Mantém a lógica de cortes sincronizados com o BPM da música.

---

### Dicas de Busca de B-Roll

**✅ Boas práticas:**
- Use termos descritivos específicos: `"DJ booth POV equalizer"`, `"vinyl record spinning turntable"`
- Combine elementos visuais: `"nightclub crowd hands up dancing"`
- Inclua termos de qualidade: `"4k"`, `"close up"`, `"cinematic"`
- Evite termos muito genéricos que retornem muitos vídeos longos/lives

**❌ Evite:**
- Termos muito amplos: `"music"`, `"party"` (muitos vídeos longos)
- Termos que geram tutoriais: `"how to DJ"`, `"mixing tutorial"`
- Palavras que geram lives: `"live set"`, `"live performance"`

### Quantidade Mínima de Vídeos

- **Recomendado**: 6-8 vídeos para variedade
- **Mínimo**: 4 vídeos (editor vai reusar clips)
- **Se falhar**: Reduza `min_videos` ou melhore `broll_idea`

## 🔧 Sistema de Cache

### Áudio (audio/tracks/)
- **Formato**: `{track_id}.mp3`
- **Cache**: Automático por track_id
- **Reutilização**: Se o arquivo existe e tem >200KB, pula download

### B-roll (broll_library/{style}/)
- **Formato**: `yt_{video_id}.mp4`
- **Cache**: Por estilo de busca (broll_idea)
- **Reutilização**: Vídeos baixados uma vez são reusados

### Blacklist de Vídeos

Em `providers/youtube.py` existe uma blacklist de vídeos indesejados:

```python
BLACKLIST_VIDEO_IDS = {
    "b2JvzT2sYhg",  # Tutorial
    "fLdnb24DgH4",  # Tutorial
    "tr4Uk7WaBKo",  # Duplicate
    # ... 9 IDs no total
}
```

**Para adicionar IDs à blacklist:**
1. Identifique o video_id no log (formato: `https://www.youtube.com/watch?v={VIDEO_ID}`)
2. Adicione ao set `BLACKLIST_VIDEO_IDS` em `providers/youtube.py`

## 📝 Exemplos de Posts Criados

### Posts 001-012 (Já Processados)

```
✅ Post 001: Peggy Gou - (It Goes Like) Nanana
✅ Post 002: Pawsa - Groove It
✅ Post 003: Chris Stussy - All Night Long
✅ Post 004: Michael Bibi - Hanging Tree
✅ Post 005: Anotr - Relax My Eyes
✅ Post 006: FISHER - Losing It
✅ Post 007: Dennis Cruz - El Sueno
✅ Post 008: Frankie Knuckles - Your Love
✅ Post 009: Cloonee - Be Good To Me
✅ Post 010: Mr. Fingers - Can You Feel It
✅ Post 011: Marshall Jefferson - Move Your Body
✅ Post 012: Stardust - Music Sounds Better With You
```

Cada post gerou:
- 3 variantes (v1.mp4, v2.mp4, v3.mp4)
- Durações: 7.4-9.7 segundos (aleatório entre 8-10s)
- Qualidade: 1080x1920 (vertical), 30fps, h264_nvenc

## 🐛 Troubleshooting

### Erro: "YouTube provider could only get X videos (need Y)"

**Causa**: Busca retornou poucos vídeos ou muitos foram filtrados.

**Soluções:**
1. Reduza `min_videos` no CSV (ex: de 6 para 4)
2. Melhore a `broll_idea` com termos mais específicos
3. Use termos que geram vídeos curtos (<1h)

**Exemplo de ajuste:**
```csv
# ❌ Ruim (muito genérico)
12,Track,Artist,afterhours club vibe,nightlife,6

# ✅ Bom (específico)
12,Track,Artist,nightclub dim lights vibe,nightlife club lounge,4
```

### Erro: "Audio download failed"

**Causa**: Track_id não encontrado no YouTube ou nome incorreto.

**Soluções:**
1. Use formato: `"Artist Track Name"` sem caracteres especiais
2. Teste a busca no YouTube manualmente
3. Use nome oficial da track

### Velocidade de renderização lenta

**Verificações:**
1. GPU está sendo usada? Procure `[fast-render]` nos logs
2. Está usando `exporter_fast.py`? (não o `exporter.py` antigo)
3. Verifique GPU no Task Manager (deve mostrar uso de Video Encode)

**Performance esperada:**
- Pass 1: 0.3-0.4s por segmento (paralelo com 4 workers)
- Pass 2: 0.3s para concat (copy codec, sem re-encode)
- Total: 0.2-0.3s por segundo de vídeo final

### Post com vídeos duplicados/ruins

**Soluções:**
1. Adicione video_id à blacklist em `providers/youtube.py`
2. Delete o folder de cache: `broll_library/{style}/`
3. Execute novamente com `--overwrite`

## 🔄 Workflow de Processamento

### 1. Download de Áudio
```
YouTube Search → yt-dlp download → extract mp3 → cache em audio/tracks/
```

### 2. Análise de Batida
```
librosa beat_track() → BPM detection → start_offset calculation
```

### 3. Download de B-roll
```
YouTube Search → filter (15s-1h, not live) → yt-dlp 60s segments → cache
```

### 4. Geração de Variantes (3x)
```
For each variant:
  - Duration: random.uniform(8.0, 10.0)
  - Edit plan: select clips from b-roll
  - Render: exporter_fast.py (2-pass)
```

### 5. Renderização (2-Pass Architecture)

**Pass 1: Segment Rendering (Parallel)**
```
For each segment (4 workers in parallel):
  - Input: 1 video file
  - Filter: crop/scale/speed/setpts
  - Encode: h264_nvenc (GPU)
  - Output: temp segment file (no audio)
Time: 0.3-0.4s per segment
```

**Pass 2: Concatenation (Fast)**
```
- Concat: all segments (demuxer concat protocol)
- Video: copy codec (NO RE-ENCODE)
- Audio: add track with AAC encoding
- Output: final MP4
Time: 0.3s total
```

**Por que é tão rápido?**
- Segmentos processados em paralelo (4 CPUs)
- Cada segmento tem filtro simples (1 input → GPU encode)
- Pass 2 usa copy codec (apenas empacota streams)
- GPU faz todo o encoding pesado

## 🎨 Configurações de Renderização

### config.py (principais parâmetros)

```python
@dataclass
class RenderConfig:
    max_duration_s: float = 9.0        # Base (sobrescrito por variante)
    clip_min_s: float = 0.5            # Duração mínima de um clip
    clip_max_s: float = 1.5            # Duração máxima de um clip
    nvenc_preset: str = "p1"           # p1=fastest, p7=slowest
    speed_min: float = 0.95            # Speed variation range
    speed_max: float = 1.05
    resolution: tuple[int, int] = (1080, 1920)  # Vertical (Instagram/TikTok)
    fps: int = 30
    video_bitrate: str = "8M"
    audio_bitrate: str = "192k"
```

### Ajustes Comuns

**Aumentar qualidade (mais lento):**
```python
nvenc_preset: str = "p4"              # Balanced
video_bitrate: str = "12M"            # Higher bitrate
```

**Aumentar velocidade (menor qualidade):**
```python
nvenc_preset: str = "p1"              # Já é o mais rápido
max_workers: int = 6                  # Mais threads (exporter_fast.py)
```

## 📦 Dependências

```
yt-dlp              # YouTube downloads
librosa             # Beat analysis
numpy               # Audio processing
ffmpeg (8.0.1)      # Video encoding (com NVENC)
```

## 🎯 Próximos Passos Sugeridos

1. **Adicionar mais posts**: Edite `posts_queue.csv` e rode batch
2. **Melhorar blacklist**: Adicione video_ids indesejados
3. **Testar diferentes estilos**: Experimente novas `broll_idea` queries
4. **Caption automation**: Configure OPENAI_API_KEY para captions automáticas
5. **Parallel batch processing**: Modificar batch_posts.py para processar N posts em paralelo

## 📈 Métricas de Performance

### Posts 001-012 (Benchmark)

- **Total de posts**: 12
- **Total de variantes**: 36 (3 por post)
- **Tempo total de vídeo**: ~300 segundos (~5 minutos de conteúdo)
- **Tempo de processamento**: ~15 minutos (incluindo downloads)
- **Velocidade média**: ~20x real-time
- **Cache hit rate**: ~80% (muitos vídeos reusados)

### Breakdown de Tempo (por post)

```
Download áudio:       ~10s  (primeira vez, depois cache)
Análise BPM:          ~2s
Download b-roll:      ~30s  (primeira vez, depois cache)
Rendering 3 variantes: ~45s  (15s por variante)
Total:                ~90s  (com cache: ~60s)
```

## 🔐 Segurança e Boas Práticas

1. **Não commitar**: `audio/tracks/`, `broll_library/`, `posts/` (grandes arquivos)
2. **API Keys**: OPENAI_API_KEY em `.env` (não no código)
3. **Backup**: Posts finais em `posts/*/output/*.mp4`
4. **Cleanup**: Delete cache periodicamente se ficar muito grande

## 📞 Comandos Úteis

### Limpar cache de b-roll de um estilo específico
```powershell
Remove-Item -Recurse "broll_library/nightclub dim lights vibe"
```

### Reprocessar um post específico
```powershell
python main.py --online --online-provider youtube `
  --online-track-id "Artist Track" `
  --online-broll-style "style" `
  --online-themes "themes" `
  --online-broll-min-videos 6 `
  --online-post-name "post_013_track" `
  --overwrite
```

### Ver posts criados
```powershell
Get-ChildItem -Path posts -Directory | Select-Object Name
```

### Ver tamanho do cache
```powershell
Get-ChildItem -Path broll_library -Recurse | Measure-Object -Property Length -Sum
Get-ChildItem -Path audio/tracks -Recurse | Measure-Object -Property Length -Sum
```

---

**Última atualização**: 2026-02-01  
**Status**: 12 posts criados (001-012) ✅  
**Sistema**: Batch processing funcional ✅  
**Performance**: 19.9-36x real-time ✅
