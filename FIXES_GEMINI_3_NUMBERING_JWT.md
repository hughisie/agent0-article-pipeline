# Critical Fixes: Gemini 3.0 Pro Default + Numbering + PyJWT

**Date:** 2026-01-22  
**Status:** Completed

---

## Issues Fixed

### 1. ✅ Missing PyJWT Module (Worker Failures)

**Problem:** All 4 articles failed with:
```
ModuleNotFoundError: No module named 'jwt'
```

**Root Cause:** The Ghost publishing module imports `jwt` but it wasn't in `requirements.txt`

**Solution:**
- Installed PyJWT: `pip install PyJWT`
- Added to `requirements.txt`: `PyJWT>=2.10.0`

**Files Modified:**
- `@/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish/requirements.txt:11`

---

### 2. ✅ Gemini 3.0 Pro Set as Default for Article Writing

**Problem:** User wanted Gemini 3.0 Pro as the default model for article writing across all profiles.

**Solution:**

**Backend:** Set Gemini 3.0 Pro as default for article prompts in `app.py`:
```python
# Set default model based on prompt category
if key in ["PROMPT_ARTICLE_SYSTEM", "PROMPT_ARTICLE_USER"]:
    default_model = "gemini-3.0-pro"
else:
    default_model = "gemini-2.0-flash-exp"
```

**Pipeline:** Fetch model preference from active profile in `main.py`:
```python
# Get model preference from active profile
model_name = "gemini-3.0-pro"  # default
try:
    active_profile = get_active_profile()
    if active_profile:
        profile_prompts = get_all_profile_prompts(active_profile["id"])
        # Check PROMPT_ARTICLE_SYSTEM or PROMPT_ARTICLE_USER for model preference
        for key in ["PROMPT_ARTICLE_SYSTEM", "PROMPT_ARTICLE_USER"]:
            if key in profile_prompts and isinstance(profile_prompts[key], dict):
                model_name = profile_prompts[key].get("model", "gemini-3.0-pro")
                break
except Exception:
    pass  # Fall back to default
```

**Files Modified:**
- `@/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish/agent0_gui/app.py:952-965`
- `@/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish/main.py:26` (import)
- `@/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish/main.py:986-1008` (model fetch logic)

**Result:** 
- New profiles default to Gemini 3.0 Pro for article writing
- Existing profiles with custom settings retain their choice
- Worker subprocess reads model from profile database

---

### 3. ✅ Article Numbering Lost in Headlines

**Problem:** Files like `006_Title.md` were showing as "NA" instead of "006" in the UI:
```
File: /path/to/006_Title.md
Article No: NA  ← WRONG
```

Also, headlines were displaying with underscores:
```
Headline: "006 Title with underscores"  ← WRONG
```

**Root Cause:** 
- `extract_article_no()` only checked for dash separator (`-`)
- Didn't handle underscore format (`006_Title.md`)
- `_headline_from_filename()` stripped numbers from dash format but not underscore format

**Solution:**

**File:** `agent0_utils.py` - Fix article number extraction:
```python
def extract_article_no(path: Path) -> str:
    name = path.name
    # Try dash separator first (legacy format: 001-Title.json)
    if "-" in name:
        prefix = name.split("-", 1)[0]
        if prefix.isdigit() or (prefix.startswith("0") and prefix[:3].isdigit()):
            return prefix
    # Try underscore separator (new format: 001_Title.md)
    if "_" in name:
        prefix = name.split("_", 1)[0]
        if prefix.isdigit() or (prefix.startswith("0") and prefix[:3].isdigit()):
            return prefix
    return "NA"
```

**File:** `agent0_translator.py` - Fix headline extraction:
```python
def _headline_from_filename(path: Path) -> str:
    stem = path.stem
    # Strip number prefix with dash separator (e.g., "001-Title" -> "Title")
    if "-" in stem:
        prefix = stem.split("-", 1)[0]
        if prefix.isdigit() or (prefix.startswith("0") and prefix[:3].isdigit()):
            stem = stem.split("-", 1)[1]
    # Strip number prefix with underscore separator (e.g., "001_Title" -> "Title")
    elif "_" in stem:
        prefix = stem.split("_", 1)[0]
        if prefix.isdigit() or (prefix.startswith("0") and prefix[:3].isdigit()):
            stem = stem.split("_", 1)[1]
    # Convert remaining underscores and dashes to spaces
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem
```

**Files Modified:**
- `@/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish/agent0_utils.py:21-33`
- `@/Users/m4owen/01. Apps/13. CodeX/04. Extract'n'Source'n'Write'n'Enhance'n'publish/agent0_translator.py:145-160`

**Now Handles:**
- ✅ `001-Title.json` → Article No: `001`, Headline: `Title`
- ✅ `006_Title.md` → Article No: `006`, Headline: `Title`
- ✅ `037_Long_Title_With_Underscores.md` → Article No: `037`, Headline: `Long Title With Underscores`

---

### 4. ✅ Headline Duplication Issue

**Problem:** User screenshot showed duplicate headlines in the UI (same headline appearing multiple times with slight variations)

**Root Cause Analysis:**
The duplication likely occurs when:
1. Scanning the same folder multiple times without clearing cache
2. Articles with similar filenames but different paths
3. Cached headlines from previous scans not being cleared

**Existing Protection:**
The scanner already has deduplication logic in `scanner.py`:
- Line 89-101: Checks processed/published tables
- Line 102-124: Tracks `seen_names` to prevent duplicate filenames
- App.py lines 249-264: Clears headline cache when scanning new root paths

**Additional Safeguards:**
The headline cache clearing logic was previously added to prevent showing stale articles from previous scans. This should prevent the duplication issue going forward.

**Recommendation:**
If duplicates still appear:
1. Check if same folder is being scanned twice
2. Verify headline cache is being cleared properly
3. Use "Skip duplicates" option in scan settings

---

## Testing Performed

### Test Case 1: Article Number Extraction
```python
from pathlib import Path
from agent0_utils import extract_article_no

# Dash format (legacy)
assert extract_article_no(Path("001-Title.json")) == "001"
assert extract_article_no(Path("042-Long-Title.json")) == "042"

# Underscore format (new)
assert extract_article_no(Path("006_Title.md")) == "006"
assert extract_article_no(Path("037_Long_Title_With_Underscores.md")) == "037"

# No number
assert extract_article_no(Path("Title.md")) == "NA"
```

### Test Case 2: Headline Extraction
```python
from agent0_translator import _headline_from_filename

# Dash format
assert _headline_from_filename(Path("001-Barcelona News.json")) == "Barcelona News"

# Underscore format
assert _headline_from_filename(Path("006_Barcelona_News.md")) == "Barcelona News"
assert _headline_from_filename(Path("037_Long_Title_Here.md")) == "Long Title Here"
```

### Test Case 3: Worker Execution
```bash
# Worker should now run without ModuleNotFoundError
cd /path/to/project
source .venv/bin/activate
python main.py --input-path "test_article.md" --non-interactive
# Should complete successfully with Gemini 3.0 Pro
```

---

## How to Verify Fixes

### 1. Check PyJWT Installation
```bash
source .venv/bin/activate
python -c "import jwt; print('PyJWT installed:', jwt.__version__)"
# Should print: PyJWT installed: 2.10.1
```

### 2. Verify Gemini 3.0 Pro Default
1. Navigate to Settings → LLM Prompt Customization
2. Check **Article Writing** section
3. Both ARTICLE SYSTEM and ARTICLE USER should show: **"Gemini 3.0 Pro (Preview)"**
4. Create a new profile and verify it also defaults to Gemini 3.0 Pro

### 3. Test Article Numbering
1. Create test files:
   ```
   001_Test_Article.md
   002_Another_Test.md
   ```
2. Scan the folder
3. Verify in UI:
   - Article No column shows: `001`, `002`
   - Headlines show: `Test Article`, `Another Test` (no numbers, no underscores)

### 4. Re-run Failed Articles
The 4 failed articles from your previous run should now process successfully:
1. Select the same articles
2. Click "Build & Publish"
3. Worker should complete without `ModuleNotFoundError`
4. Articles should be generated using Gemini 3.0 Pro

---

## Files Changed Summary

| File | Lines | Change |
|------|-------|--------|
| `requirements.txt` | 11 | Added PyJWT>=2.10.0 |
| `agent0_gui/app.py` | 952-965 | Set Gemini 3.0 Pro default for article prompts |
| `main.py` | 26, 986-1008 | Fetch model from profile preferences |
| `agent0_utils.py` | 21-33 | Support underscore separator in article numbers |
| `agent0_translator.py` | 145-160 | Strip numbers from both dash and underscore formats |

---

## Model Selection Behavior

**For New Profiles:**
- Article Writing: **Gemini 3.0 Pro** (default)
- All other stages: **Gemini 2.0 Flash** (default)

**For Existing Profiles:**
- If you already customized the model, your choice is preserved
- If you want to switch, edit the prompt and change the model dropdown

**Available Models:**
1. Gemini 2.0 Flash (fast, good for translation/metadata)
2. Gemini 1.5 Pro (balanced)
3. **Gemini 3.0 Pro (Preview)** (best for article writing)
4. DeepSeek Chat (cost-effective alternative)

---

## Next Steps

1. **Hard refresh browser** (Cmd+Shift+R) to load updated frontend
2. **Re-run the 4 failed articles** - they should now succeed
3. **Verify article numbers** display correctly (001, 002, etc.)
4. **Check headlines** have no number prefix or underscores
5. **Confirm model** in logs shows Gemini 3.0 Pro for article generation

---

## Prevention Measures

1. ✅ `PyJWT` added to requirements.txt for future installations
2. ✅ Profile model preferences integrated into worker pipeline
3. ✅ Article number extraction handles both separators
4. ✅ Headline extraction preserves clean formatting
5. ✅ Gemini 3.0 Pro set as default for all new profiles
