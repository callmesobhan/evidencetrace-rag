"""Canonical documents.

A :class:`Document` owns the *canonical text* (see ``textnorm.canonical_text``). Every character
offset stored anywhere in the system indexes into ``Document.text``, and ``sha256`` pins the exact
text those offsets are valid for.
"""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from evidencetrace.abbreviations import find_abbreviations
from evidencetrace.textnorm import canonical_text

# heading line -> canonical section name
HEADINGS: dict[str, str] = {
    "abstract": "abstract",
    "summary": "abstract",
    "introduction": "introduction",
    "background": "introduction",
    "methods": "methods",
    "method": "methods",
    "materials and methods": "methods",
    "patients and methods": "methods",
    "results": "results",
    "findings": "results",
    "discussion": "discussion",
    "limitations": "discussion",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
}

_HEADING_LINE = re.compile(
    r"^[ \t]*+(?:#{1,4}[ \t]+)?(?:\d+\.?[ \t]+)?(?P<h>[A-Za-z][A-Za-z ]{2,30}?)[ \t]*+:?[ \t]*+$",
    re.MULTILINE,
)


def heading_name(line: str) -> str | None:
    """Canonical section name if ``line`` is a section heading, else None."""
    m = _HEADING_LINE.match(line)
    if not m:
        return None
    return HEADINGS.get(m.group("h").strip().lower())


class Section(BaseModel):
    name: str
    start: int
    end: int


class Document(BaseModel):
    doc_id: str
    title: str
    text: str
    sha256: str
    sections: list[Section] = Field(default_factory=list)
    source: str | None = None
    abbreviations: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_text(
        cls,
        doc_id: str,
        raw_text: str,
        *,
        title: str | None = None,
        source: str | None = None,
        sections: list[Section] | None = None,
    ) -> Document:
        """``sections`` lets a structured parser (JATS) supply real section boundaries instead of
        having them guessed from heading lines. Offsets must index the *canonical* text."""
        text = canonical_text(raw_text)
        if sections is not None and canonical_text(raw_text) != raw_text:
            raise ValueError("explicit sections require already-canonical text")
        if title is None:
            title = next((ln.strip() for ln in text.splitlines() if ln.strip()), doc_id)
        return cls(
            doc_id=doc_id,
            title=title,
            text=text,
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            sections=sections if sections is not None else detect_sections(text),
            source=source,
            abbreviations=find_abbreviations(text),
        )

    def section_at(self, offset: int) -> str:
        for sec in self.sections:
            if sec.start <= offset < sec.end:
                return sec.name
        return "other"


def detect_sections(text: str) -> list[Section]:
    marks: list[tuple[int, str]] = []
    for m in _HEADING_LINE.finditer(text):
        name = HEADINGS.get(m.group("h").strip().lower())
        if name:
            marks.append((m.start(), name))
    if not marks:
        return [Section(name="other", start=0, end=len(text))]
    sections: list[Section] = []
    if marks[0][0] > 0:
        sections.append(Section(name="front", start=0, end=marks[0][0]))
    for i, (start, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        sections.append(Section(name=name, start=start, end=end))
    return sections
