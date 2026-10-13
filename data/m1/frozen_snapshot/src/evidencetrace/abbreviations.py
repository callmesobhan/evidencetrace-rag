"""Within-paper abbreviation definitions ("global longitudinal strain (GLS)").

Papers define their own shorthand once and then use it everywhere. Results sentences say "GLS"; a
reader asks about "global longitudinal strain". Expanding abbreviations *using the same paper's own
definitions* closes that gap without importing topics from elsewhere in the paper (which is what
indexing the title did, and why that was rejected).

This is the Schwartz-Hearst (2003) heuristic: an abbreviation in parentheses whose letters match, in
order, the initial letters of the words just before it.
"""

from __future__ import annotations

import re

_PAREN = re.compile(r"[(\[]([^()\[\]]{2,12})[)\]]")


def _valid_short(s: str) -> bool:
    if " " in s or not (2 <= len(s) <= 10) or not s[0].isalnum():
        return False
    return any(c.isalpha() for c in s) and any(c.isupper() or c.isdigit() for c in s)


def _best_long_form(short: str, long_text: str) -> str | None:
    s_idx, l_idx = len(short) - 1, len(long_text) - 1
    while s_idx >= 0:
        c = short[s_idx].lower()
        if not c.isalnum():
            s_idx -= 1
            continue
        while l_idx >= 0 and (
            long_text[l_idx].lower() != c
            or (s_idx == 0 and l_idx > 0 and long_text[l_idx - 1].isalnum())  # first letter starts a word
        ):
            l_idx -= 1
        if l_idx < 0:
            return None
        l_idx -= 1
        s_idx -= 1
    start = long_text.rfind(" ", 0, l_idx + 1) + 1
    return long_text[start:]


def find_abbreviations(text: str) -> dict[str, str]:
    """{"GLS": "global longitudinal strain", ...} from definitions found in ``text``."""
    out: dict[str, str] = {}
    for m in _PAREN.finditer(text):
        short = m.group(1).strip()
        if not _valid_short(short):
            continue
        words = text[max(0, m.start() - 160) : m.start()].split()
        max_words = min(len(short) + 5, len(short) * 2)
        long = _best_long_form(short, " ".join(words[-max_words:]))
        if long and len(long.split()) <= max_words and len(long) > len(short):
            out.setdefault(short, long.strip(" ,;:"))
    return out


def aliases_for(sentence: str, abbreviations: dict[str, str]) -> list[str]:
    """Search-only synonyms for a sentence: long forms of abbreviations it uses and vice versa."""
    low = sentence.lower()
    found = []
    for short, long in abbreviations.items():
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(short)}(?![A-Za-z0-9])", sentence):
            found.append(long)
        elif long.lower() in low:
            found.append(short)
    return found
