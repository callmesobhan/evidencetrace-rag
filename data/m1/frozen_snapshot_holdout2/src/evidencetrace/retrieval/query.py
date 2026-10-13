"""Pull the intervention slot out of a question, when the question has a recognisable shape.

"What is the effect of Drug Zeta on systolic blood pressure?" -> intervention "Drug Zeta", outcome "systolic blood
pressure". Free-form questions do not parse and simply get no slot handling (the previous behaviour).
"""

from __future__ import annotations

import re

_PATTERNS = (
    re.compile(r"^\s*(?:what\s+(?:is|are|was|were)\s+)?the\s+(?:effects?|impact|efficacy|influence)\s+of\s+"
               r"(?P<int>.+?)\s+on\s+(?P<out>.+?)\s*[?.]?\s*$", re.I),
    re.compile(r"^\s*(?:does|do|did|can|could|will)\s+(?P<int>.+?)\s+(?:reduce|lower|increase|improve|raise|decrease|"
               r"affect|change|prevent|cause|worsen)s?\s+(?P<out>.+?)\s*[?.]?\s*$", re.I),
)


def parse_slots(query: str) -> tuple[str, str] | None:
    """(intervention phrase, outcome phrase), or None if the question has no recognised shape."""
    for rx in _PATTERNS:
        m = rx.match(query)
        if m:
            return m["int"].strip(), m["out"].strip()
    return None
