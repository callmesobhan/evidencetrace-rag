"""Sentence-aligned chunking for the dense index.

Chunks are exact slices of the canonical text, so a retrieved chunk can be mapped back to the
findings whose spans fall inside it.
"""

from __future__ import annotations

from dataclasses import dataclass

from evidencetrace.ingest.document import Document
from evidencetrace.ingest.sentences import split_sentences


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    start: int
    end: int
    text: str
    section: str


def chunk_document(doc: Document, max_chars: int = 1200, overlap_sentences: int = 1) -> list[Chunk]:
    sents = split_sentences(doc)
    chunks: list[Chunk] = []
    i = 0
    while i < len(sents):
        j = i
        while j < len(sents) and (j == i or sents[j].end - sents[i].start <= max_chars):
            j += 1
        start, end = sents[i].start, sents[j - 1].end
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{len(chunks)}",
                doc_id=doc.doc_id,
                start=start,
                end=end,
                text=doc.text[start:end],
                section=sents[i].section,
            )
        )
        if j >= len(sents):
            break
        i = max(j - overlap_sentences, i + 1)
    return chunks
