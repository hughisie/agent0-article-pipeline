"""
Programmatic readability checker aligned with Yoast SEO thresholds.

Detects:
  - Passive voice percentage (target: <10%)
  - Long sentence percentage (>20 words, target: <25%)
  - Transition word usage (target: >30%)

If thresholds are exceeded, triggers a targeted LLM rewrite pass.
"""

import re
from html.parser import HTMLParser


# ── HTML stripping ──────────────────────────────────────────────────────
class _TagStripper(HTMLParser):
    """Strip HTML tags and Gutenberg block comments, keeping only text."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_comment(self, data):
        pass  # Drop Gutenberg <!-- wp:... --> comments

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        # Add sentence boundary after block-level elements
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self._parts.append(".")

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def strip_html(html: str) -> str:
    """Return plain text from HTML/Gutenberg content."""
    s = _TagStripper()
    s.feed(html)
    return s.get_text()


# ── Sentence splitting ──────────────────────────────────────────────────
_SENTENCE_END = re.compile(
    r'(?<=[.!?])\s+(?=[A-Z"\u201c])'  # Split on sentence-ending punctuation followed by capital
)
_ABBREV = re.compile(r'\b(?:Mr|Mrs|Ms|Dr|Prof|St|vs|etc|approx|i\.e|e\.g)\.\s', re.IGNORECASE)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, handling common abbreviations."""
    # Protect abbreviations by replacing their periods
    protected = _ABBREV.sub(lambda m: m.group(0).replace(". ", "·ABBR· "), text)
    parts = _SENTENCE_END.split(protected)
    sentences = []
    for p in parts:
        s = p.replace("·ABBR· ", ". ").strip()
        if s and len(s.split()) >= 3:  # Skip fragments
            sentences.append(s)
    return sentences


# ── Passive voice detection ─────────────────────────────────────────────
# Yoast checks for: form of "to be" + past participle
_BE_FORMS = r'\b(?:is|are|was|were|be|been|being|has been|have been|had been|will be|would be|could be|should be|might be|may be|can be)\b'
_PAST_PARTICIPLE = r'\b\w+(?:ed|en|ung|wn|ght|lt|pt|ft|nt|xt)\b'
_PASSIVE_PATTERN = re.compile(
    rf'({_BE_FORMS})\s+(?:\w+\s+)?({_PAST_PARTICIPLE})',
    re.IGNORECASE
)

# Common false positives to exclude
_FALSE_POSITIVE_PHRASES = {
    "is expected", "are expected", "is needed", "are needed",
    "is located", "are located", "is based", "are based",
    "is known", "are known", "is called", "are called",
    "is designed", "are designed", "is required", "are required",
    "is considered", "is concerned", "is related",
}


def is_passive_sentence(sentence: str) -> bool:
    """Check if a sentence contains passive voice construction."""
    match = _PASSIVE_PATTERN.search(sentence)
    if not match:
        return False
    # Check for false positives
    matched_text = match.group(0).lower().strip()
    for fp in _FALSE_POSITIVE_PHRASES:
        if fp in matched_text:
            return False
    return True


# ── Transition words ────────────────────────────────────────────────────
_TRANSITION_WORDS = [
    # Cause/effect
    "as a result", "because", "consequently", "due to", "for this reason",
    "hence", "since", "so that", "therefore", "thus",
    # Comparison
    "equally", "in comparison", "likewise", "similarly",
    # Contrast
    "although", "but", "despite", "even though", "however",
    "in contrast", "instead", "nevertheless", "nonetheless",
    "on the other hand", "rather", "still", "whereas", "while", "yet",
    # Addition
    "additionally", "also", "besides", "furthermore", "in addition",
    "moreover", "what is more",
    # Time/sequence
    "after", "afterwards", "before", "during", "eventually",
    "finally", "first", "firstly", "in the meantime", "later",
    "meanwhile", "next", "previously", "secondly", "subsequently",
    "then", "thirdly",
    # Emphasis
    "above all", "certainly", "especially", "importantly",
    "in fact", "indeed", "notably", "of course", "particularly",
    # Summary/conclusion
    "all in all", "in conclusion", "in short", "in summary",
    "overall", "to sum up", "ultimately",
    # Example
    "for example", "for instance", "in particular", "specifically",
    "such as",
]

# Build regex: match at word boundaries, case-insensitive
_TRANSITION_PATTERN = re.compile(
    r'\b(?:' + '|'.join(re.escape(tw) for tw in sorted(_TRANSITION_WORDS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE
)


def has_transition_word(sentence: str) -> bool:
    """Check if a sentence contains at least one transition word/phrase."""
    return bool(_TRANSITION_PATTERN.search(sentence))


# ── Main analysis ───────────────────────────────────────────────────────
def analyse_readability(html_content: str) -> dict:
    """
    Analyse HTML content for Yoast-style readability metrics.
    
    Returns:
        {
            "total_sentences": int,
            "passive_count": int,
            "passive_pct": float,
            "passive_sentences": list[str],
            "long_count": int,
            "long_pct": float,
            "long_sentences": list[str],
            "transition_count": int,
            "transition_pct": float,
            "word_count": int,
            "passes_passive": bool,   # <10%
            "passes_length": bool,    # <25%
            "passes_transitions": bool,  # >30%
            "all_pass": bool,
        }
    """
    text = strip_html(html_content)
    sentences = split_sentences(text)
    total = len(sentences)
    if total == 0:
        return {
            "total_sentences": 0, "passive_count": 0, "passive_pct": 0.0,
            "passive_sentences": [], "long_count": 0, "long_pct": 0.0,
            "long_sentences": [], "transition_count": 0, "transition_pct": 0.0,
            "word_count": 0, "passes_passive": True, "passes_length": True,
            "passes_transitions": True, "all_pass": True,
        }

    passive_sentences = [s for s in sentences if is_passive_sentence(s)]
    long_sentences = [s for s in sentences if len(s.split()) > 20]
    transition_sentences = [s for s in sentences if has_transition_word(s)]
    word_count = len(text.split())

    passive_pct = (len(passive_sentences) / total) * 100
    long_pct = (len(long_sentences) / total) * 100
    transition_pct = (len(transition_sentences) / total) * 100

    passes_passive = passive_pct <= 10.0
    passes_length = long_pct <= 25.0
    passes_transitions = transition_pct >= 30.0
    transitions_not_overstuffed = transition_pct <= 50.0

    # Detect consecutive transition word stacking (3+ in a row)
    consecutive_stacks = 0
    max_consecutive = 0
    current_run = 0
    for s in sentences:
        if has_transition_word(s):
            current_run += 1
            max_consecutive = max(max_consecutive, current_run)
        else:
            if current_run >= 3:
                consecutive_stacks += 1
            current_run = 0
    if current_run >= 3:
        consecutive_stacks += 1

    return {
        "total_sentences": total,
        "passive_count": len(passive_sentences),
        "passive_pct": round(passive_pct, 1),
        "passive_sentences": passive_sentences[:5],
        "long_count": len(long_sentences),
        "long_pct": round(long_pct, 1),
        "long_sentences": long_sentences[:5],
        "transition_count": len(transition_sentences),
        "transition_pct": round(transition_pct, 1),
        "transitions_overstuffed": not transitions_not_overstuffed,
        "consecutive_stacks": consecutive_stacks,
        "max_consecutive_transitions": max_consecutive,
        "word_count": word_count,
        "passes_passive": passes_passive,
        "passes_length": passes_length,
        "passes_transitions": passes_transitions,
        "passes_transition_cap": transitions_not_overstuffed,
        "all_pass": passes_passive and passes_length and passes_transitions and transitions_not_overstuffed,
    }


# ── Targeted rewrite prompt builder ─────────────────────────────────────
def build_readability_fix_prompt(
    wp_block_content: str,
    analysis: dict,
) -> dict | None:
    """
    Build a targeted rewrite prompt ONLY for failing readability checks.
    Returns None if all checks pass.
    """
    if analysis["all_pass"]:
        return None

    issues = []

    if analysis.get("transitions_overstuffed") or analysis.get("consecutive_stacks", 0) > 0:
        issues.append(
            f"TRANSITION WORD OVERUSE: Currently {analysis['transition_pct']}% (must be 30-45%, NOT higher).\n"
            f"  The writing sounds robotic because too many sentences start with transition words.\n"
            f"  REMOVE transition words from some sentences to bring usage down to 35-40%.\n"
            f"  - Remove transition words where the sentence makes sense without them\n"
            f"  - Keep transition words only where they genuinely connect ideas\n"
            f"  - NEVER have 3+ consecutive sentences starting with transition words\n"
            f"  - BAD: 'Consequently, X. Furthermore, Y. Moreover, Z. Additionally, W.'\n"
            f"  - GOOD: 'X happened. Consequently, Y occurred. Z followed. Moreover, W emerged.'"
        )

    if not analysis["passes_passive"]:
        passive_examples = "\n".join(
            f'    PASSIVE: "{s}"' for s in analysis["passive_sentences"]
        )
        issues.append(
            f"PASSIVE VOICE: Currently {analysis['passive_pct']}% (must be under 10%).\n"
            f"  Rewrite these sentences to use ACTIVE voice:\n{passive_examples}\n"
            f"  Examples of passive → active rewrites:\n"
            f'    PASSIVE: "The station was evacuated by firefighters" → ACTIVE: "Firefighters evacuated the station"\n'
            f'    PASSIVE: "The report was published by the council" → ACTIVE: "The council published the report"\n'
            f'    PASSIVE: "Residents were told to stay indoors" → ACTIVE: "Authorities told residents to stay indoors"\n'
            f'    PASSIVE: "The decision was made after a meeting" → ACTIVE: "Officials made the decision after a meeting"\n'
            f'    PASSIVE: "The building has been described as unsafe" → ACTIVE: "Inspectors described the building as unsafe"'
        )

    if not analysis["passes_length"]:
        long_examples = "\n".join(
            f'    LONG ({len(s.split())} words): "{s[:120]}..."' for s in analysis["long_sentences"]
        )
        issues.append(
            f"SENTENCE LENGTH: Currently {analysis['long_pct']}% over 20 words (must be under 25%).\n"
            f"  Split or shorten these sentences:\n{long_examples}\n"
            f"  Techniques:\n"
            f"    - Split compound sentences at conjunctions (and, but, while, which)\n"
            f"    - Remove unnecessary qualifiers and filler words\n"
            f"    - Turn subordinate clauses into separate sentences\n"
            f'    Example: "The fire broke out at the station on Monday afternoon and was quickly extinguished by emergency services who arrived within minutes."\n'
            f'    → "The fire broke out at the station on Monday afternoon. Emergency services arrived within minutes and quickly extinguished the blaze."'
        )

    if not analysis["passes_transitions"] and not analysis.get("transitions_overstuffed"):
        issues.append(
            f"TRANSITION WORDS: Currently {analysis['transition_pct']}% (must be 30-45%).\n"
            f"  Add transition words at the START of some sentences. Choose from:\n"
            f"    however, meanwhile, therefore, additionally, moreover, consequently\n"
            f"  Add them naturally — maximum 2 consecutive transition-word openers."
        )

    issues_text = "\n\n".join(issues)

    system_prompt = (
        "You are a readability editor. You fix ONLY the specific readability issues listed below.\n"
        "Preserve ALL existing HTML structure, links, Gutenberg block comments, and factual content.\n"
        "Make MINIMAL changes — only rewrite the sentences that fail the checks.\n"
        "Output the COMPLETE wp_block_content with fixes applied. No JSON wrapping, just the raw HTML content.\n"
        "Do NOT add new information, links, or change the meaning of any sentence."
    )

    user_prompt = (
        f"Fix these readability issues in the article below:\n\n"
        f"{issues_text}\n\n"
        f"RULES:\n"
        f"  - ONLY fix the specific issues listed above\n"
        f"  - Preserve ALL <!-- wp:... --> block comments exactly as they are\n"
        f"  - Preserve ALL <a href=...> links exactly as they are\n"
        f"  - Preserve ALL <img> tags exactly as they are\n"
        f"  - Keep British English spelling\n"
        f"  - Do NOT add bold, italic, or any new formatting\n"
        f"  - Do NOT remove or add paragraphs/headings\n"
        f"  - Output ONLY the fixed HTML content, nothing else\n\n"
        f"ARTICLE CONTENT:\n{wp_block_content}"
    )

    return {"system_prompt": system_prompt, "user_prompt": user_prompt}
