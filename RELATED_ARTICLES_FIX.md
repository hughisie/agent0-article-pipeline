# Related Articles Bug Fix

## Problem Identified (Article 41982)

**Issue:** Terrace heaters article contained:
1. **Repeated linking phrase**: "That debate has been building for months — we covered it in..."
2. **Irrelevant link**: Renfe evacuation inquiry article linked when it has nothing to do with terrace heaters

## Root Causes

### 1. Related Articles Prompt (PROMPT_RELATED_USER)
- **Too lenient** on relevance checking
- Doesn't require semantic topic overlap
- Only checks for "useful background, context, or continuation" without strict relevance

### 2. Article Writing Prompt (PROMPT_ARTICLE_USER)
- **No instructions** to avoid repetitive linking phrases
- Says "weave in a natural way" but doesn't specify uniqueness
- No guidance on introducing each link differently

## Solution: Enhanced Prompts

### Fix 1: Stricter Related Articles Selection

**Add to PROMPT_RELATED_USER:**

```
CRITICAL RELEVANCE REQUIREMENTS:
  - Related articles MUST share the same core topic, theme, or subject matter as the new article
  - Do NOT select articles just because they mention the same city or government entity
  - Examples of GOOD relevance:
    * New article about terrace heaters ban → Related: previous article about terrace heater regulations
    * New article about metro expansion → Related: previous metro construction updates
  - Examples of BAD relevance (DO NOT LINK):
    * New article about terrace heaters → DON'T link to: Renfe trains, bureaucracy reforms, unrelated government announcements
    * New article about beach rules → DON'T link to: traffic regulations, housing policies

  - Ask yourself: "Would a reader interested in THIS article find THAT article genuinely useful?"
  - If the connection requires mental gymnastics to explain, DO NOT SELECT IT
  - It's better to return ZERO links than to return irrelevant ones

  - Verify semantic overlap: do both articles discuss the same policy area, industry, or specific issue?
  - Geographic proximity alone (same city) is NOT sufficient for relevance
  - Institutional overlap alone (same government) is NOT sufficient for relevance
```

### Fix 2: Unique Link Introductions

**Add to PROMPT_ARTICLE_USER (in the related articles section):**

```
CRITICAL LINKING REQUIREMENTS:
  - Each related article link MUST be introduced with a UNIQUE phrase or sentence
  - NEVER repeat the same linking pattern (e.g., "we covered it in...", "as discussed in...")
  - Vary your linking style for each reference:
    * First link: Natural contextual reference (e.g., "The city previously addressed similar concerns about...")
    * Second link: Background reference (e.g., "This follows earlier action on...")
    * Third link: Continuation reference (e.g., "The issue connects to broader questions about...")

  - Use different sentence structures for each link
  - Avoid formulaic patterns like "That debate has been building for months — we covered it in X"
  - Make each link introduction flow naturally from the surrounding paragraph
  - If you cannot introduce a link naturally and uniquely, skip it rather than force it

EXAMPLES OF GOOD LINKING VARIETY:
  ❌ BAD (repetitive):
    "That debate has been building for months — we covered it in streamlining municipal bureaucracy."
    "That debate has been building for months — we covered it in scrutiny of public service operations."

  ✅ GOOD (varied):
    "The city previously addressed similar concerns when streamlining municipal bureaucracy."
    "This follows earlier scrutiny of public service operations, which raised questions about oversight."
```

## Implementation Steps

1. **Update PROMPT_RELATED_USER** (Related Articles Selection)
   - Add strict relevance requirements
   - Add examples of good vs bad relevance
   - Emphasize semantic topic overlap

2. **Update PROMPT_ARTICLE_USER** (Article Writing)
   - Add unique linking requirements
   - Provide examples of varied linking styles
   - Warn against repetitive patterns

3. **Test with problematic case**
   - Re-process article 41982
   - Verify no irrelevant links
   - Verify no repeated linking phrases

## Recommended Prompt Updates

### For PROMPT_RELATED_USER (add after line 49):

```
CRITICAL RELEVANCE REQUIREMENTS:
  - Related articles MUST share the same core topic or policy area
  - Geographic or institutional proximity alone is NOT sufficient
  - Ask: "Would someone reading about terrace heaters find an article about train evacuations relevant?" NO.
  - Semantic topic overlap is REQUIRED (both about same industry, regulation type, or specific issue)
  - If unsure about relevance, do NOT select the article
  - Return empty list rather than force irrelevant connections
```

### For PROMPT_ARTICLE_USER (add to related articles section around line 97):

```
  - IMPORTANT: Each link must have a UNIQUE introduction - never repeat linking phrases
  - Vary your linking style: contextual reference, background note, continuation point
  - Example BAD: Using "we covered it in..." twice
  - Example GOOD: "The city previously...", "This follows earlier...", "Related concerns emerged when..."
```

## Quick Fix via UI

Users can now edit these prompts through the Profile Management system:

1. Navigate to **LLM Prompt Customization**
2. Expand **Related Articles** section
3. Edit `PROMPT_RELATED_USER` to add relevance requirements
4. Expand **Article Writing** section
5. Edit `PROMPT_ARTICLE_USER` to add unique linking requirements
6. Save and test

## Testing Checklist

- [ ] Related articles selection rejects obviously irrelevant articles
- [ ] No repeated linking phrases in generated articles
- [ ] Each link has unique introduction
- [ ] Links still flow naturally in article body
- [ ] Empty related list returned when no truly relevant articles found
