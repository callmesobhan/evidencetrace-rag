"""Offset-preserving sentence splitting.

Every returned span satisfies ``text[start:end]`` == the sentence, so provenance never depends on
re-tokenised or re-joined strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from evidencetrace.ingest.document import Document, heading_name

_BLOCK = re.compile(r"[^\n]+(?:\n(?![ \t]*\n)[^\n]+)*")  # runs of non-blank lines
# a sentence may end with citation markers before the break: "... in KFRT.[11] Chlorthalidone was ..."
_BOUNDARY = re.compile(r"(?<=[.!?])(?:\[[\d,\s\u2013\u2012-]+\])*(?P<ws>\s+)(?=[A-Z0-9\[(\"“])")
_ABBREV = {
    "al.", "vs.", "e.g.", "i.e.", "fig.", "figs.", "eq.", "no.", "dr.", "approx.", "cf.", "ca.",
    "etc.", "st.", "ref.", "refs.",
}  # fmt: skip
_INITIAL = re.compile(r"^[A-Z]\.$")
_NAME_LEADERS = {"by", "of", "and", "with", "from", "to", "in", "at", "for", "as", "see", "per"}


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int
    text: str
    section: str


def split_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for block in _BLOCK.finditer(text):
        b0, b1 = block.span()
        first_nl = text.find("\n", b0, b1)
        first_line = text[b0:first_nl] if first_nl != -1 else text[b0:b1]
        if heading_name(first_line):
            if first_nl == -1:
                continue
            b0 = first_nl + 1
        spans.extend(_split_block(text, b0, b1))
    return spans


def _split_block(text: str, start: int, end: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    cursor = start
    for m in _BOUNDARY.finditer(text, start, end):
        words = text[cursor : m.start()].split()
        last_word = words[-1] if words else ""
        if last_word.lower() in _ABBREV:
            continue
        # a lone capital + period is an initial ("J. Smith", "Smith J. A.") only when it follows a
        # capitalised word; after a lower-case one it is a label ("HF stage A. Therefore ...")
        if _INITIAL.match(last_word) and (
            len(words) == 1
            or words[-2][:1].isupper()
            or _INITIAL.match(words[-2])
            or words[-2].lower() in _NAME_LEADERS  # "trial by J. Smith"
        ):
            continue
        out.append((cursor, m.start("ws")))  # markers stay with the sentence they cite
        cursor = m.end()
    out.append((cursor, end))
    return [(s, e) for s, e in out if text[s:e].strip()]


def split_sentences(doc: Document) -> list[Sentence]:
    sentences = []
    for s, e in split_spans(doc.text):
        raw = doc.text[s:e]
        lead = len(raw) - len(raw.lstrip())
        s, e = s + lead, e - (len(raw) - len(raw.rstrip()))
        sentences.append(Sentence(s, e, doc.text[s:e], doc.section_at(s)))
    return sentences
