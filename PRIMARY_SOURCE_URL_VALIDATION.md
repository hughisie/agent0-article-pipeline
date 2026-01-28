# Primary Source URL Validation - Issue Analysis & Solution

## Problem Discovered

**Article ID:** 41944
**Topic:** Barcelona public holidays 2026 calendar
**Issue:** Incorrect primary source URL embedded in published article

### Incorrect vs Correct URLs:
- **Embedded (Wrong):** `https://govern.cat/salapremsa/notes-premsa/445831/govern-aprova-calendari-festes-laborals-lany-2026`
- **Correct:** `https://govern.cat/salapremsa/notes-premsa/691002/govern-aprova-calendari-festes-laborals-lany-2026`

### Key Observation:
- Same URL slug/path: `govern-aprova-calendari-festes-laborals-lany-2026`
- Different ID numbers: `445831` vs `691002`
- The wrong URL (445831) was likely an older/different article with similar slug

## Root Cause Analysis

### 1. **Primary Source Finding Process**
The system uses Gemini 2.5 Flash with Search Grounding to find primary sources:
- LLM performs Google searches based on article content
- Finds URLs that match the topic
- **Problem:** URL slug matches but ID doesn't guarantee correct article

### 2. **No Content Validation**
- URLs are accepted based on search results
- No validation that the URL content actually matches the article
- No check that URLs return HTTP 200
- No comparison when multiple similar URLs exist

### 3. **Registry Storage Without Verification**
- Found URLs are stored in `primary_sources_registry.json`
- Once in registry, they're reused for similar articles
- Incorrect URLs propagate to multiple articles

### 4. **Direct Embedding Without Post-Validation**
- LLM embeds primary source URLs directly in article content
- No final validation before publishing
- Incorrect links go live on WordPress

## Impact

### SEO & Credibility:
- Broken or incorrect source links damage credibility
- Google may penalize for linking to 404s or wrong content
- Users lose trust when sources don't match article claims

### User Experience:
- Readers can't verify article claims
- Confused users when source doesn't match article topic

### Legal/Editorial:
- Misattribution of sources
- Potential copyright/citation issues

## Solutions Implemented

### 1. **New Validation Module: `primary_source_validator.py`**

Comprehensive URL validation that checks:

#### Basic Validation:
- HTTP status code (must be 200)
- Not redirecting to error pages
- Not soft-404s (pages that say "not found" but return 200)

#### Content Matching:
- **Title Similarity:** Compares article title with source page title (SequenceMatcher)
- **Content Matching:** Extracts key terms from both and calculates overlap
- **Keyword Verification:** Ensures expected keywords appear in source

#### URL Intelligence:
- Detects ID number mismatches (e.g., 445831 vs 691002)
- Warns about redirects to different article IDs
- Extracts and validates publication dates

#### Features:
```python
def validate_primary_source_url(
    url: str,
    article_title: str,
    article_content: str,
    expected_keywords: Optional[list[str]] = None
) -> SourceValidation
```

Returns:
- `is_valid`: Boolean pass/fail
- `content_match_score`: 0-1 similarity score
- `title_match_score`: 0-1 title similarity
- `issues`: List of problems (404, wrong content, etc.)
- `warnings`: List of concerns (low match, redirects, etc.)
- `extracted_title` & `extracted_date`: Metadata from source

### 2. **Registry Cleanup Tool: `fix_primary_source_urls.py`**

Script to audit and clean the registry:

```bash
python fix_primary_source_urls.py
```

Features:
- Validates all URLs in registry
- Reports invalid URLs (404s, errors)
- Shows warnings (redirects, status issues)
- Offers to automatically remove invalid entries
- Creates backup before making changes

### 3. **Enhanced LLM Prompts**

Updated `PRIMARY_USER` prompt with explicit instructions:

**New Instructions:**
```
CRITICAL URL VALIDATION:
  - ALWAYS verify the URL returns HTTP 200 (not 404, 403, or error page)
  - ALWAYS verify the page content actually matches the article topic and date
  - If you find multiple URLs with similar paths but different ID numbers,
    CHECK EACH ONE and select the one that best matches the article date and content
  - Prefer URLs with dates that match the article's timeframe
  - If the page title/headline doesn't match, it's likely the wrong URL
  - Double-check that official announcement URLs are current, not outdated versions
  - Verify the source contains the specific information mentioned in the article
```

### 4. **Existing URL Validator Integration**

The system already had `url_validator.py` with:
- HTTP status checking
- Redirect detection
- Soft-404 detection (error signatures in HTML)
- PDF content-type validation
- Retry logic for transient errors

**Now integrated more tightly with primary source finding.**

## Usage & Implementation

### For New Articles (Automatic):

The enhanced prompt will automatically:
1. Find multiple candidate URLs
2. Validate each one
3. Check content matches article topic
4. Prefer most recent/accurate URL

### Manual Validation (When Needed):

```python
from primary_source_validator import validate_primary_source_url

# Validate a URL against article content
result = validate_primary_source_url(
    url="https://govern.cat/salapremsa/notes-premsa/691002/govern-aprova-calendari-festes-laborals-lany-2026",
    article_title="Barcelona public holidays 2026 calendar",
    article_content="The Government of Catalonia approved the work calendar...",
    expected_keywords=["Barcelona", "2026", "festius", "holidays"]
)

if result.is_valid:
    print(f"✓ Valid URL (score: {result.content_match_score:.2f})")
else:
    print(f"✗ Invalid: {result.issues}")
```

### Compare Similar URLs:

```python
from primary_source_validator import compare_similar_urls

# When you have two URLs with same slug but different IDs
better_url = compare_similar_urls(
    url1="https://govern.cat/salapremsa/notes-premsa/445831/govern-aprova-calendari-festes-laborals-lany-2026",
    url2="https://govern.cat/salapremsa/notes-premsa/691002/govern-aprova-calendari-festes-laborals-lany-2026",
    article_title="Barcelona public holidays 2026",
    article_content="..."
)
print(f"Better match: {better_url}")
```

### Clean Registry:

```bash
# Check for invalid URLs in registry
python fix_primary_source_urls.py

# It will:
# 1. Test all URLs
# 2. Report issues
# 3. Offer to remove invalid ones
# 4. Create backup before changes
```

## Best Practices Going Forward

### 1. **Before Publishing:**
- Review primary source URLs in preview
- Verify they match article topic and date
- Check they return 200 (not 404)

### 2. **Periodic Registry Maintenance:**
```bash
# Run monthly
python fix_primary_source_urls.py
```

### 3. **Monitor Published Articles:**
- Check WordPress for broken source links
- Update registry when official URLs change

### 4. **When Finding Wrong URLs:**
1. Note the correct URL
2. Remove wrong URL from registry
3. Republish article with correct link

## Technical Details

### Validation Scoring:

**Content Match Score:**
- Extracts key terms from both article and source
- Filters common words (para, este, aquest, etc.)
- Calculates term overlap ratio
- Score ≥ 0.2 required for validation

**Title Match Score:**
- Uses SequenceMatcher for fuzzy matching
- Handles different languages and formats
- Score ≥ 0.4 considered good match

### Validation Thresholds:

```python
# URL is valid if:
is_valid = (
    status_code == 200 and
    no_issues and
    (content_match_score >= 0.2 or title_match_score >= 0.4)
)
```

### Error Detection:

**Hard Errors (Block URL):**
- HTTP 4xx/5xx status codes
- Redirect to homepage
- Page contains "404" or "not found"
- No extractable content

**Warnings (Flag for Review):**
- Low content match (< 0.2)
- Title mismatch (< 0.3)
- Missing expected keywords
- Redirect to different article ID

## Example: Fixing Article 41944

### Step 1: Validate Current URL
```bash
python -c "
from primary_source_validator import validate_primary_source_url
result = validate_primary_source_url(
    'https://govern.cat/salapremsa/notes-premsa/445831/govern-aprova-calendari-festes-laborals-lany-2026',
    'Barcelona public holidays 2026',
    'Government approved work calendar...'
)
print(f'Valid: {result.is_valid}')
print(f'Issues: {result.issues}')
"
```

### Step 2: Test Correct URL
```bash
python -c "
from primary_source_validator import validate_primary_source_url
result = validate_primary_source_url(
    'https://govern.cat/salapremsa/notes-premsa/691002/govern-aprova-calendari-festes-laborals-lany-2026',
    'Barcelona public holidays 2026',
    'Government approved work calendar...'
)
print(f'Valid: {result.is_valid}')
print(f'Match score: {result.content_match_score:.2f}')
"
```

### Step 3: Update Registry
1. Remove wrong URL (445831) from `primary_sources_registry.json`
2. Add correct URL (691002)
3. Regenerate article with correct source

## Files Created/Modified

### New Files:
- `primary_source_validator.py` - Comprehensive URL validation
- `fix_primary_source_urls.py` - Registry cleanup tool
- `PRIMARY_SOURCE_URL_VALIDATION.md` - This documentation

### Modified Files:
- `prompts.py` - Enhanced PRIMARY_USER prompt with validation instructions

### Existing Files (Already Available):
- `url_validator.py` - Basic HTTP validation (now integrated better)
- `primary_source_finder.py` - LLM-based source finding
- `primary_sources_registry.json` - Source URL registry

## Future Enhancements

### 1. **Automatic Correction:**
- Detect similar URLs with different IDs
- Auto-test all variants
- Choose best match automatically

### 2. **Real-Time Validation:**
- Validate URLs during article generation
- Reject invalid URLs before embedding
- Suggest alternatives if validation fails

### 3. **ML-Based Matching:**
- Train model on correct URL patterns
- Learn from past corrections
- Predict best URL from candidates

### 4. **URL Monitoring:**
- Periodic checks of all registered URLs
- Alert when sources become unavailable
- Suggest archived versions (Wayback Machine)

## Conclusion

The incorrect URL issue in article 41944 highlighted a critical gap in URL validation. The implemented solutions provide:

1. **Prevention:** Enhanced LLM prompts to find correct URLs
2. **Validation:** Comprehensive content matching before acceptance
3. **Detection:** Tools to audit registry and find issues
4. **Correction:** Framework for fixing and monitoring sources

These improvements significantly reduce the risk of publishing articles with incorrect or broken primary source links, maintaining credibility and SEO performance.
