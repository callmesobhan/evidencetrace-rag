"""Who/what is a number about? Tagging intervention / comparator / outcome / population.

``FieldTagger`` is the seam between the deterministic numeric layer and a learned model.
``RuleFieldTagger`` is the offline baseline and the reference the BERT tagger is evaluated against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Fields:
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    population: str | None = None
    confidence: float = 0.0  # 0..1, how much to trust the tagging


class FieldTagger(Protocol):
    name: str

    def tag(self, sentence: str) -> Fields: ...


_SVO = re.compile(
    r"""^(?:(?:In|Among)\s+[^,]{3,80},\s+)?
        (?P<int>[A-Z][^,;()]{1,60}?)\s+
        (?:  (?:did|does|do)\s+not\s+(?:significantly\s+)?(?:reduce|lower|decrease|increase|improve|raise|change|affect)
           | (?:was|were)\s+associated\s+with\s+(?:a\s+)?(?:significantly\s+)?(?:lower|reduced|higher|increased|greater|improved)
           | (?:significantly\s+|markedly\s+|modestly\s+)?(?:reduced|lowered|decreased|increased|improved|raised|worsened)
           | had\s+no\s+(?:significant\s+)?(?:effect|impact)\s+on
        )\s+
        (?:the\s+)?(?:(?:risk|rate|rates|incidence)\s+of\s+)?
        (?P<out>[^,;()]+?)
        (?:\s+(?:compared\s+(?:with|to)|versus|vs\.?|relative\s+to)\s+(?P<cmp>[^,;()]+?))?
        (?:\s+(?:in|among)\s+(?P<pop>[^,;()]+?))?
        \s*(?:[(,;]|\.?$)""",
    re.VERBOSE,
)

_STAT_FOR = re.compile(
    r"(?:ratio|difference|risk)\s+(?:for|of|in)\s+(?:the\s+)?(?P<out>[^,;().]+?)\s+(?:was|were|is)\b"
)


_NOT_A_NAME = re.compile(r"[\[\]()%]|\b(?:was|were|is|are|but|which|that|than|had|has|have|not|numerically)\b", re.I)


def _clean(s: str | None) -> str | None:
    """A field is a short noun phrase. Anything clause-like means the pattern misfired: return None."""
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip(" ,.;")
    s = re.sub(r"^(?:the|a|an)\s+", "", s, flags=re.IGNORECASE)
    if not s or len(s.split()) > 8 or _NOT_A_NAME.search(s):
        return None
    return s


class RuleFieldTagger:
    name = "rules-v1"

    def tag(self, sentence: str) -> Fields:
        flat = re.sub(r"\s+", " ", sentence)
        m = _SVO.match(flat)
        if m:
            fields = dict(
                intervention=_clean(m["int"]),
                outcome=_clean(m["out"]),
                comparator=_clean(m["cmp"]),
                population=_clean(m["pop"]),
            )
        else:
            m2 = _STAT_FOR.search(flat)
            fields = dict(outcome=_clean(m2["out"]) if m2 else None)
        filled = sum(fields.get(k) is not None for k in ("intervention", "outcome", "comparator"))
        return Fields(**fields, confidence=filled / 3)
