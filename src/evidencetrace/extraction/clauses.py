"""Which words of a sentence belong to an estimate, and in which role.

Retrieval used to treat a sentence as a bag of words, so "Drug Zeta did not change stroke risk, whereas placebo
increased myocardial infarction (HR 1.40)" answered a question about Zeta and myocardial infarction with the *placebo*
arm's hazard ratio. Two cheap, conservative structural cues repair the common cases:

* ``effect_clause``: split at ``whereas``, ``, while``, ``in contrast``, ``conversely`` - and at ``;`` only when an estimate
  sits on BOTH sides of it - and keep the clause that holds the estimate. Words in the other clause are not evidence about
  this estimate. ("but"/"although" are NOT split points: "Zeta lowered SBP, but not DBP (MD -2)" has an elliptical
  subject. A ``;`` that merely separates statistics - "...mg/L; p = 0.026)" or "...with the drug; adjusted mean difference
  1.45" - is not a boundary either; both mistakes lost answerable queries when tried.)
* ``comparator_spans``: text after "versus / vs / compared with / relative to / than / against" is the reference arm.
  A term that appears *only* there ("placebo" in "Zeta vs placebo on SBP") is not the intervention.

Both are deliberately lexical. They do not understand language; they remove the most common ways a word can be present
without being the subject. Limits are listed in docs/known-issues.md.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_CONTRAST = re.compile(r"\bin contrast\b|\bconversely\b|\bwhereas\b|,\s*while\b", re.I)
_COMPARATOR = re.compile(r"\b(?:versus|vs\.?|compared\s+(?:with|to)|relative\s+to|than|against)\s+", re.I)
# a reference arm is a short noun phrase: it ends at punctuation or at a preposition that starts a new phrase
_COMPARATOR_END = re.compile(r"[,;:()\[\]]|\b(?:in|on|for|at|after|over|during|among|regarding|by|from|were|was|is|are)\b", re.I)
_MAX_COMPARATOR_WORDS = 6
# Words that name a reference arm wherever they occur: a between-arm estimate is never an estimate "of" the placebo.
# ("control" alone is NOT here: "blood pressure control" is an outcome. "control group/arm" is.)
_CONTROL_ARM = re.compile(
    r"\b(?:placebo|usual\s+care|standard\s+(?:of\s+)?care|sham|vehicle|no\s+treatment|no\s+intervention|wait[- ]?list|"
    r"control\s+(?:group|arm)s?)\b",
    re.I,
)


def effect_clause(sentence: str, est_start: int, est_end: int, estimate_starts: Sequence[int] = ()) -> str:
    """The clause of ``sentence`` that contains the estimate at ``[est_start, est_end)`` (sentence-relative offsets).

    ``estimate_starts`` are the starts of every estimate in the sentence; a ``;`` splits only if one lies on each side.
    """
    semis = [m for m in re.finditer(";", sentence)
             if any(e < m.start() for e in estimate_starts) and any(e > m.end() for e in estimate_starts)]
    cuts = sorted([*semis, *_CONTRAST.finditer(sentence)], key=lambda m: m.start())
    cuts = [m for m in cuts if not _inside_brackets(sentence, m.start())]
    if not cuts:
        return sentence
    lo, hi = 0, len(sentence)
    for m in cuts:
        if m.end() <= est_start:
            lo = m.end()
        elif m.start() >= est_start and hi == len(sentence):
            hi = m.start()
    clause = sentence[lo:hi].strip(" ,;")
    return clause if len(clause.split()) >= 3 else sentence  # a fragment is not a clause: fall back to the sentence


def _inside_brackets(text: str, pos: int) -> bool:
    return text.count("(", 0, pos) > text.count(")", 0, pos) or text.count("[", 0, pos) > text.count("]", 0, pos)


def comparator_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of the reference arm(s) named in ``text``."""
    spans = []
    for m in _COMPARATOR.finditer(text):
        start = m.end()
        end_m = _COMPARATOR_END.search(text, start)
        end = end_m.start() if end_m else len(text)
        words = list(re.finditer(r"\S+", text[start:end]))
        if len(words) > _MAX_COMPARATOR_WORDS:
            end = start + words[_MAX_COMPARATOR_WORDS - 1].end()
        if end > start:
            spans.append((start, end))
    return spans


def split_roles(text: str) -> tuple[str, str]:
    """(text outside any reference arm, text of the reference arms)."""
    spans = sorted(set(comparator_spans(text)) | {(m.start(), m.end()) for m in _CONTROL_ARM.finditer(text)})
    merged: list[tuple[int, int]] = []
    for s, e in spans:  # overlapping spans (a control word inside a "vs ..." phrase) become one
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    spans = merged
    main, cmp_parts, pos = [], [], 0
    for s, e in spans:
        main.append(text[pos:s])
        cmp_parts.append(text[s:e])
        pos = e
    main.append(text[pos:])
    return " ".join(main), " ".join(cmp_parts)
