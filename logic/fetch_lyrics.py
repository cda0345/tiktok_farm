import os
import asyncio
import urllib.parse
import requests
from pathlib import Path
from playwright.async_api import async_playwright
from typing import Union

# Constants
LYRICS_FILENAME = "lyrics.lrc"

async def fetch_lrclib(query: str):
    """Fetches lyrics from LRCLIB API (Primary)."""
    url = f"https://lrclib.net/api/search?q={urllib.parse.quote(query)}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            results = response.json()
            if results:
                synced = [r for r in results if r.get('syncedLyrics')]
                if synced:
                    return synced[0]['syncedLyrics']
        return None
    except Exception as e:
        print(f"  [LRCLIB] Error: {e}")
        return None

async def fetch_lyricsify(browser, query: str):
    """Fetches lyrics from Lyricsify via Playwright (Secondary)."""
    page = await browser.new_page()
    url = f"https://www.lyricsify.com/search?q={urllib.parse.quote(query)}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        first_result = await page.query_selector("a.title")
        if not first_result:
            await page.close()
            return None
        
        track_url = await first_result.get_attribute("href")
        if not track_url.startswith("http"):
            track_url = "https://www.lyricsify.com" + track_url
            
        await page.goto(track_url, wait_until="networkidle")
        lrc_text = await page.inner_text("#lyrics-content")
        if not lrc_text:
            lrc_text = await page.get_attribute("#lyrics", "value")
            
        await page.close()
        if lrc_text and "[" in lrc_text:
            return lrc_text.strip()
        return None
    except Exception as e:
        print(f"  [Lyricsify] Error: {e}")
        await page.close()
        return None

async def fetch_megalobiz(browser, query: str):
    """Fetches lyrics from Megalobiz via Playwright (Fallback)."""
    page = await browser.new_page()
    url = f"https://www.megalobiz.com/search/all?search={urllib.parse.quote(query)}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        first_result = await page.query_selector("a.entity_name")
        if not first_result:
            await page.close()
            return None
            
        track_url = await first_result.get_attribute("href")
        if not track_url.startswith("http"):
            track_url = "https://www.megalobiz.com" + track_url
            
        await page.goto(track_url, wait_until="networkidle")
        lrc_text = await page.inner_text("#lrc_display_block")
        await page.close()
        
        if lrc_text and "[" in lrc_text:
            return lrc_text.strip()
        return None
    except Exception as e:
        print(f"  [Megalobiz] Error: {e}")
        await page.close()
        return None

async def get_lyrics_async(track_id: str):
    """Orchestrates fetching lyrics from all sources."""
    query = track_id.replace("_", " ")
    
    # 1. Try LRCLIB (No browser needed)
    lrc = await fetch_lrclib(query)
    if lrc:
        return lrc, "LRCLIB"

    # 2. Try Scrapers (Need browser)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            print(f"  Trying Lyricsify for: {query}...")
            lrc = await fetch_lyricsify(browser, query)
            if lrc:
                await browser.close()
                return lrc, "Lyricsify"
            
            print(f"  Trying Megalobiz for: {query}...")
            lrc = await fetch_megalobiz(browser, query)
            if lrc:
                await browser.close()
                return lrc, "Megalobiz"
            
            await browser.close()
    except Exception as e:
        print(f"  Scraper error: {e}")
        
    return None, None

def fetch_and_save_lyrics(post_dir: Union[str, Path], track_id: str):
    """Entry point for other scripts to fetch and save lyrics."""
    post_dir = Path(post_dir)
    lrc_path = post_dir / LYRICS_FILENAME
    
    if lrc_path.exists():
        return True

    print(f"  Fetching lyrics for: {track_id}")
    try:
        # Check if already in an event loop (e.g. running inside an async app)
        try:
            loop = asyncio.get_running_loop()
            # If we are already in a loop, we might need a different approach, 
            # but for our CLI scripts, we usually aren't.
            # For simplicity, we'll assume we are running in synchronous main scripts.
            lrc, source = asyncio.run(get_lyrics_async(track_id))
        except RuntimeError:
            lrc, source = asyncio.run(get_lyrics_async(track_id))
            
        if lrc:
            lrc_path.write_text(lrc, encoding="utf-8")
            print(f"  ✓ Found on {source} and saved to {LYRICS_FILENAME}")
            return True
        else:
            print(f"  ✗ No synced lyrics found for {track_id}")
            return False
    except Exception as e:
        print(f"  Error fetching lyrics: {e}")
        return False

# For batch processing of all posts
async def main():
    from post_parser import parse_caption_file
    posts_root = Path("posts")
    if not posts_root.exists(): return
    post_dirs = sorted([d for d in posts_root.iterdir() if d.is_dir()])
    
    for d in post_dirs:
        try:
            spec = parse_caption_file(str(d))
            fetch_and_save_lyrics(d, spec.track_id)
        except:
            continue

if __name__ == "__main__":
    asyncio.run(main())

