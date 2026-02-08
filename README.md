# Short-form video generator (House + Lifestyle)

**Current Status (Feb 2026):**
- 🎤 **TikTok Lyrics Mode**: New specialized engine for synchronized chorus videos
- 📝 **Auto-Lyrics**: Multi-source scraper (LRCLIB, Lyricsify, Megalobiz) for `.lrc` files
- ✅ 20 working posts (001-013, 016, 018-019, 021-022)
- 🚫 4 posts failed permanently - audio unavailable on YouTube (014, 015, 017, 020)
- ⚡ Fast 2-pass GPU rendering: 17.6x - 50.4x real-time speed (h264_nvenc)
- 🥁 Rhythm Engine: New pulse-based cuts synchronized with BPM
- 🔄 Seamless Loops: Perfect infinite loops for Instagram Reels
- 📚 B-roll library: 120+ videos across 6 categories (Added `city_drive` focus)
- 🚫 Blacklist: 41 video IDs filtered

## Project Architecture (For AI Agents)

If you are a new AI agent taking over this workspace, here is the technical core:

### 1. The TikTok Lyrics Pipeline (`tiktok_lyrics.py`)
This is the current active development focus. It generates 10-15s clips focused on song choruses with synchronized "TikTok-style" captions.
- **Entry point**: `python tiktok_lyrics.py --post <id> --start <seconds> --duration <seconds>`
- **Logic**: It parses `lyrics.lrc`, snaps the start time to the nearest beat (BPM synchronized), and renders using the "Fast Exporter".
- **Visuals**: Uses **Bahnschrift** font, yellow/white highlights, and `city_drive` b-roll by default.

### 2. Fast Rendering Engine (`exporter_fast.py`)
Uses a 2-pass approach to maximize speed and sync:
- **Pass 1**: Renders small chunks of video with `drawtext` filters (lyrics) to a temp folder.
- **Pass 2**: Concatenates chunks and merges with audio via FFmpeg.
- **Critical Fix**: Always keep `-i audio.mp3` before `-i concat.txt` in the final command to ensure correct seeking (`-ss`) and prevent silence.

### 3. Lyrics Acquisition (`fetch_lyrics.py`)
Downloads synced lyrics (`.lrc`) automatically using:
1. **LRCLIB** (Primary API)
2. **Lyricsify** (Scraping via Playwright)
3. **Megalobiz** (Scraping via Playwright)

### 4. B-roll & Themes
- **Storage**: `broll_library/` contains high-quality categorized clips.
- **Mapping**: `broll_categories.py` handles the logic of which video fits which song vibe.

### 5. Gossip Post Pipeline (v1 format)
The Gossip pipeline is now strictly standardized to the **v1.mp4** format (5.0 seconds, editorial typography).
- **Entry point**: `python scripts/create_gossip_posts_br.py`
- **Logic**: It scrapes Brazilian celebrity feeds (Contigo, Ofuxico, Terra, IG), summarizes the news using AI, and overlays structured text layers.
- **Visuals**: Uses **Avenir Next Condensed** for a premium "portal" look.

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py --help
```

## Quick Start - Batch Processing

**Best for multiple posts:**

```powershell
python batch_posts.py posts_queue.csv
```

See [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md) for complete documentation.

## Run Single Post

```powershell
python main.py --posts-dir .\posts --broll-dir .\broll --audio-dir .\audio\tracks
```

## Online pipeline (downloads + caption + render)

This project supports an online pipeline with multiple providers:
- **YouTube**: Downloads video/audio clips for b-roll (default, recommended)
- **Pexels**: Legal stock video provider
- **Local**: Uses existing files in broll_library/<style>

### Important Files

- **tiktok_lyrics.py**: Main entry point for the new synchronized lyrics mode.
- **fetch_lyrics.py**: Automated tool to download `.lrc` files for all posts.
- **lrc_parser.py**: Logic to translate timestamps from LRC files into render events.
- **exporter_fast.py**: High-performance GPU renderer (handles `drawtext` for lyrics).
- **broll_categories.py**: Maps 40+ search queries to 6 macro-categories.
- **providers/youtube.py**: Contains BLACKLIST_VIDEO_IDS (41 IDs).
- **batch_posts.py**: Process multiple standard posts from CSV.
- **BATCH_PROCESSING_GUIDE.md**: Complete documentation for batching.

### B-roll Library Structure (6 categories, 110 videos)

```
broll_library/
├── nightlife_crowd/      27 videos (hands up, dancing, energy)
├── dj_booth/            21 videos (DJ mixing, turntables)
├── abstract_aesthetic/   17 videos (aesthetic vibes, nightclub)
├── nightlife_light/      16 videos (silhouettes, dim lights)
├── city_drive/          15 videos (night drive, city lights)
└── luxury_bar/          14 videos (lounge, VIP atmosphere)
```

**Category Mapping System:**
- Queries automatically route to category folders
- Prevents duplicate downloads
- Enables cache reuse across similar queries
- 41 blacklisted video IDs automatically filtered

Environment variables:

```powershell
$env:OPENAI_API_KEY = "<your_openai_key>"  # Optional: for captions
$env:PEXELS_API_KEY = "<your_pexels_key>"  # Optional: if using Pexels
```

### Using Pexels provider (stock video):

```powershell
python main.py --online --online-provider pexels --online-track-id house_127bpm_01 --online-broll-style aesthetic --online-themes nightlife,luxury,city
```

Note: Pexels may have limited nightlife content compared to YouTube.

### Using YouTube provider (downloads clips):

**Recommended method - searches YouTube for audio + b-roll:**

```powershell
python main.py --online --online-provider youtube --online-track-id "artist_trackname" --online-broll-style "nightclub crowd energy" --online-broll-min-videos 4 --online-themes nightlife,energy
```

**B-roll query examples that map to categories:**
- `"nightclub hands up dancing"` → abstract_aesthetic
- `"nightclub silhouettes dim lights"` → nightlife_light
- `"DJ mixing turntables close up"` → dj_booth
- `"city nightdrive urban lights"` → city_drive
- `"nightclub lounge vibe"` → luxury_bar
- `"nightclub crowd clapping energy"` → nightlife_crowd

When using `--online-provider youtube`, the audio track will also be downloaded from YouTube if not found locally.

## Advanced Editing Features (New!)

### 1. Rhythm-Sync Engine
The generator analyzes the BPM of the track and creates cuts that follow musical phrases (4-8 beats).
- **Random Pulse Styles**: Clips can be 1 beat long (normal), 1/2 beat (fast/high-energy), or 2 beats (slow/vibey).
- **Rhythmic Intensity**: The system automatically varies intensity between phrases, preventing a repetitive feel.

### 2. Seamless Infinite Loop
Videos are engineered for Reels/TikTok "infinite discovery":
- **Frame-Perfect Split**: The first and last segments of the video use the same B-roll clip, split precisely so that when the video loops, the motion is continuous and the transition is invisible.
- **Beat Alignment**: The total duration is calculated to a multiple of the beat period, ensuring the audio and video loop stay in sync forever.

**Performance:** Expect 17.6x - 50.4x real-time rendering speed (GPU-accelerated h264_nvenc).

### Batch Processing (Recommended)

Process multiple posts from CSV:

```powershell
python batch_posts.py posts_queue.csv
```

CSV format:
```csv
post_num,track_name,artist,broll_idea,themes,min_videos
1,Nanana,Peggy Gou,nightclub hands up dancing,nightlife energy,4
2,Underwater,Chris Lake,DJ mixing turntables close up,dj techno,4
```

See [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md) for details.

### Using local provider (existing files):

```powershell
python main.py --online --online-provider local --online-track-id house_127bpm_01 --online-broll-style nightlife_crowd --online-broll-min-videos 4 --online-themes nightlife,luxury
```

Style must match category folder name (nightlife_crowd, dj_booth, city_drive, abstract_aesthetic, nightlife_light, luxury_bar).

If the track MP3 is not already in `audio/tracks/<track_id>.mp3`, you can provide a local file to copy:

```powershell
python main.py --online --online-track-id house_127bpm_01 --online-track-file .\audio\tracks\house_127bpm_01.mp3
```

### Terminal monitoring

- While downloading, the provider prints per-file progress (MB / %).
- While rendering, FFmpeg output is streamed live (`-stats`) so you can watch frame/time progress.

## Optional: Generate caption.txt with OpenAI (cheapest default model)

Set your key via environment variable (do NOT put it in code):

```powershell
$env:OPENAI_API_KEY = "<your_key_here>"
```

Generate `caption.txt` for one post folder:

```powershell
python main.py --only post_001 --init-caption --init-track-id house_127bpm_01 --init-themes nightlife,luxury,city
```

Caption format (in each post folder):

- Line 1: caption text
- Line 2: hashtags
- Line 3: `track_id=<track_id>`
- Line 4: `themes=nightlife,luxury,city`

Note: if `caption_spec.txt` exists in the post folder, it is used as the spec; `caption.txt` may be a human-facing final caption.

## Known Limitations

**Failed Posts (Audio Not Available on YouTube):**
- Post 014: Butch - Acid Arab
- Post 015: Harry Romero - Daydreaming
- Post 017: CamelPhat - Techno CID Remix
- Post 020: Jaydee - Plastic Dreams

These tracks could not be found on YouTube. To process them, manually add audio files to `audio/tracks/` with matching track IDs.

**Blacklisted Videos (41 IDs):**
See `providers/youtube.py` BLACKLIST_VIDEO_IDS for complete list. These videos are automatically filtered during download (jazz lounges, disco balls, tutorials, wrong vibes).

## Troubleshooting

**"No suitable audio found":**
- Track not available on YouTube
- Try alternative track name formats: `artist_track` vs `track_artist`
- Manually download MP3 and place in `audio/tracks/<track_id>.mp3`

**"YouTube provider could only get X videos":**
- Query too specific, try broader terms
- Use multi-query approach (see `download_more_broll.py` example)
- Check if videos are blacklisted

**"This video is not available":**
- YouTube video removed or region-locked
- Will be skipped automatically, no action needed

**Rendering too slow:**
- Ensure GPU drivers updated (h264_nvenc requires NVIDIA GPU)
- Check GPU usage with Task Manager during render
- Expected: 17.6x - 50.4x real-time speed

For complete troubleshooting guide, see [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md)

prompt padrao

"Crie um novo post no formato TikTok Lyrics (Short Sync):

Música: Chew Fu & Mousse T. - Purple Rain (Mousse T's Home A Lone Mix) [Feat. Steve Clisby] (feat. Steve Clisby).mp3
Vibe/Tema: city drive/nightlife
Formato: Vídeo de 15 segundos com letras sincronizadas (LRC).
Ação: Execute o pipeline online para baixar b-rolls e use o script de lyrics para renderizar a versão curta."
execute no terminal em primeiro plano