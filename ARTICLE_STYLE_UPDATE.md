# Article Writing Style Update - British Journalism

## ✅ Changes Applied

The article-writing prompts have been completely rewritten to produce **clear, modern news articles** instead of academic policy papers.

---

## What Changed

### Previous Style
- Wired magazine tech journalism style
- Sophisticated, storytelling-driven
- Technical sophistication focus
- Long, complex sentences

### New Style
- **Modern British newspaper journalism** (Guardian/BBC News style)
- Clear, concise, accessible
- Prioritises readability and mobile-first
- Short paragraphs, active voice, simple language

---

## New Writing Rules

### 1. Opening Sentence
**Start with concrete impact on people:**
- ✅ "One in three people using public transport in Barcelona now travels on a discounted or social ticket."
- ❌ "Barcelona's transport system has undergone significant changes..."

### 2. Paragraph Structure
- **One idea per paragraph**
- **Maximum 2-3 sentences per paragraph**
- Short, punchy, mobile-friendly

### 3. Active Voice
**Put people and institutions at the start:**
- ✅ "The government is using cheaper tickets to reduce car use."
- ❌ "Fare policy is being used as a lever to reduce car use."

### 4. Simple Language
**Plain English over academic wording:**
- ❌ BANNED: "structural reconfiguration", "institutional message", "funding architecture", "lever", "ambition is to"
- ✅ USE: "The council plans to...", "The government will..."

### 5. Statistics
**Number first, then meaning:**
- ✅ "33% of all passengers now use discounted fares. That shows subsidised travel is no longer marginal."

### 6. Sentence Length
- If a sentence has more than one comma, split it
- Aim for natural, spoken rhythm
- Break up complex sentences

### 7. Explain Policy Simply
**Write as if explaining to a commuter:**
- ✅ "The State pays 20% of the discount. The Generalitat covers the remaining 30%."

### 8. Subheadings (H2/H3)
**Answer real reader questions:**
- ✅ "Who qualifies for these tickets?"
- ✅ "Who pays for the discounts?"
- ✅ "What's changing with ticket technology?"
- ❌ "Policy Implementation Framework"

### 9. Tone
- Confident, journalistic, factual
- NO ceremonial or inflated language
- NO academic framing

### 10. Banned Phrases

**NEVER USE THESE:**
- ❌ "have cause for celebration"
- ❌ "That debate has been building for months"
- ❌ "excited the community"
- ❌ "will be closely following"
- ❌ "marks a significant milestone"
- ❌ "in an exciting development"
- ❌ "structural reconfiguration"
- ❌ "institutional message"
- ❌ "funding architecture"
- ❌ "lever for change"
- ❌ "the ambition is to"
- ❌ "the objective is to"
- ❌ "this demonstrates that"

---

## Yoast SEO Compliance

**All Yoast requirements are MAINTAINED:**

✅ Focus keyphrase in first paragraph  
✅ Focus keyphrase in at least one H2  
✅ Meta title (max 60 chars) includes keyphrase  
✅ Meta description (max 145 chars) includes keyphrase  
✅ Proper heading hierarchy (H1 → H2 → H3)  
✅ Readability optimised (short sentences, short paragraphs)  
✅ Internal and external linking  
✅ Mobile-first readability  

---

## Files Modified

### 1. `/article_writer.py`
- **Lines 16-23:** Updated `system_message` to prioritise clarity and British journalism style
- **Lines 29-105:** Completely rewritten `user_message` with 10 detailed writing rules
- **Maintained:** All SEO requirements and Gutenberg block structure

---

## How It Works

### For All Profiles
The updated prompts are the **default** for all article generation. They apply to:
- **Profile A** (if you have multiple profiles)
- **Profile B** (if you have multiple profiles)
- Any new profiles created

### Per-Profile Customisation
If you want different styles per profile:
1. Go to http://localhost:9000
2. Navigate to **Profile Management → Show Prompts**
3. Expand **"Article Writing"** category
4. Click **"Edit"** on `PROMPT_ARTICLE_SYSTEM` or `PROMPT_ARTICLE_USER`
5. Customise per profile
6. Click **"Save"**

---

## Testing

### Before (Old Style)
```
"Barcelona's public transport system has undergone a significant 
structural reconfiguration, with institutional messaging emphasising 
the leverage of fare policy as a mechanism to reduce private vehicle 
dependency. The ambition is to demonstrate that subsidised travel..."
```

### After (New Style)
```
"One in three people using public transport in Barcelona now travels 
on a discounted or social ticket.

The government is using cheaper tickets to reduce car use. 33% of all 
passengers now use discounted fares. That shows subsidised travel is 
no longer marginal.

The State pays 20% of the discount. The Generalitat covers the 
remaining 30%."
```

---

## Final Check Criteria

Every article must pass these tests:

1. ✅ **Mobile test:** Easily readable on a phone
2. ✅ **Newspaper test:** Sounds like The Guardian or BBC News, not a policy report
3. ✅ **Spoken test:** Every sentence passes "would you say this out loud?"
4. ✅ **Yoast test:** Scores well on all Yoast SEO criteria
5. ✅ **British English:** Spelling and grammar are British

---

## Benefits

### Reader Experience
- **Faster comprehension** - Short paragraphs, clear language
- **Better mobile reading** - Optimised for phone screens
- **More engaging** - Active voice, concrete details

### SEO
- **Same Yoast compliance** - All SEO requirements maintained
- **Better readability scores** - Short sentences help SEO
- **More natural keyword use** - Keywords flow naturally

### Editorial Quality
- **Professional journalism** - Sounds like major newspapers
- **Consistent quality** - Clear rules reduce variability
- **Easier to edit** - Simple language is easier to refine

---

## Rollout

- ✅ **Status:** Live in production
- ✅ **Applies to:** All new articles generated
- ✅ **Backward compatible:** Existing articles unchanged
- ✅ **Profile support:** Works with custom profile prompts
- ✅ **Documentation:** This file + inline comments

---

## Summary

**Before:** Academic, sophisticated, complex  
**After:** Clear, modern, accessible British journalism

**SEO:** Fully maintained  
**Readability:** Dramatically improved  
**Mobile:** Optimised  
**Tone:** Professional newspaper standard

The system will now produce articles that read like **The Guardian** or **BBC News**, not policy documents.
