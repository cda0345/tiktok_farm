# GitHub Actions Workflow Diagnostics

## 🔧 CRITICAL FIXES (Feb 8, 2026 - 6:00 PM)

### Issues Found & Fixed:

1. **❌ Problem: Script created 19 posts instead of 3**
   - **Cause**: Loop with `for skip in range(5)` × 4 feeds = 20 potential posts
   - **Fix**: Changed to `while count < max_tests` with proper break conditions
   - **Status**: ✅ FIXED - Now respects `--count` parameter

2. **❌ Problem: FFmpeg `text_w` option not found**
   - **Cause**: Used `text_w` for auto line wrapping (only in FFmpeg 5.0+)
   - **GitHub Actions uses**: Ubuntu with older FFmpeg version
   - **Fix**: Reverted to manual line wrapping using Python's `textwrap`
   - **Status**: ✅ FIXED - Now compatible with all FFmpeg versions

3. **✅ Enhancement: Skip duplicate folders**
   - Now checks if `post_dir.exists()` before creating
   - Prevents regenerating the same post multiple times

### Test Results:
```bash
✅ Script now stops at desired count (tested with --count 1, 2, 3)
✅ Videos render successfully without text_w errors
✅ Telegram notifications working
✅ Duplicate detection working
```

---

## Changes Made (Feb 8, 2026)

### Issue
The gossip scheduler workflow was showing failed runs (X marks) in GitHub Actions.

### Fixes Applied

1. **Added Diagnostic Workflow** (`.github/workflows/diagnose.yml`)
   - Run manually via GitHub Actions UI
   - Tests all dependencies, API connectivity, and feed availability
   - Helps identify specific failure points

2. **Improved Main Workflow** (`.github/workflows/gossip_scheduler.yml`)
   - Added detailed logging to the generator step
   - Shows Python version, FFmpeg version, directory structure
   - Better error handling with explicit exit codes
   - Fixed artifact upload paths: `gossip_posts_br/**/*.mp4` (was looking in wrong subdirectories)
   - Fixed cleanup paths to match actual video locations

### How to Diagnose Issues

#### 1. Run the Diagnostic Workflow
Go to: https://github.com/cda0345/tiktok_farm/actions/workflows/diagnose.yml
- Click "Run workflow" button
- Wait for it to complete
- Check each step for failures:
  - ✓ System dependencies (ffmpeg)
  - ✓ Python packages installation
  - ✓ Telegram API connectivity
  - ✓ RSS feed availability

#### 2. Check Main Workflow Logs
Go to: https://github.com/cda0345/tiktok_farm/actions/workflows/gossip_scheduler.yml
- Click on the latest failed run
- Look for the "Run generator" step
- Check for specific errors:
  - **Module not found**: Missing dependency in requirements.txt
  - **API error**: OpenAI or Telegram credentials issue
  - **Feed error**: RSS feed unavailable or format changed
  - **FFmpeg error**: Video rendering issue

#### 3. Verify Secrets
Go to: https://github.com/cda0345/tiktok_farm/settings/secrets/actions
Ensure these are set:
- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### Common Issues & Solutions

#### Issue: "Module not found"
**Solution**: Add missing package to `requirements.txt` and push

#### Issue: Telegram API fails
**Solution**: 
1. Verify bot token is still valid
2. Check bot hasn't been blocked/deleted
3. Test bot manually: `https://api.telegram.org/bot<TOKEN>/getMe`

#### Issue: No feeds available
**Solution**:
- Brazilian gossip sites may be down temporarily
- Try running diagnostic workflow to see which feeds work
- Consider adding more feed sources to `BR_GOSSIP_FEEDS`

#### Issue: OpenAI API quota exceeded
**Solution**:
- Check OpenAI usage dashboard
- Reduce `--count` parameter in workflow (currently 3)
- Consider using cheaper model in `core/ai_client.py`

### Testing Locally

```bash
# Activate environment
source .venv/bin/activate

# Test single post generation
python scripts/create_gossip_posts_br.py --count 1

# Test specific source
python scripts/create_gossip_posts_br.py --source ofuxico --count 1
```

### Schedule Details

The workflow runs at these times (UTC → Brasília BRT -3):
- **15:00 UTC** = 12:00 BRT (noon)
- **21:00 UTC** = 18:00 BRT (evening)
- **00:00 UTC** = 21:00 BRT (night)

You can also trigger manually:
1. Go to Actions tab
2. Select "Gossip Scheduler (BR)"
3. Click "Run workflow"

### Next Steps

1. **Push these changes** ✓ (Already done)
2. **Run diagnostic workflow** to identify the specific issue
3. **Check the logs** from the next scheduled run (or manual trigger)
4. **Fix the root cause** based on diagnostic results

### Files Modified
- `.github/workflows/gossip_scheduler.yml` - Enhanced logging and fixed paths
- `.github/workflows/diagnose.yml` - New diagnostic workflow
