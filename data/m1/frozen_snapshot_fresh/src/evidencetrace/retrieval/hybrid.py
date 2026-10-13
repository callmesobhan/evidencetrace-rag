"""Hybrid retrieval: reciprocal-rank fusion of lexical finding hits and dense chunk hits.

Dense retrieval works on *chunks* (what embedding models are good at); findings are linked back to
chunks through character offsets, so no fuzzy matching is involved. Coverage always comes from the
lexical side: a dense similarity score says "related", not "this actually reports your outcome".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from evidencetrace.retrieval.lexical import Hit, LexicalFindingRetriever


@dataclass(frozen=True)
class ChunkHit:
    doc_id: str
    start: int
    end: int
    score: float


class ChunkRetriever(Protocol):
    def retrieve_chunks(self, query: str, k: int) -> list[ChunkHit]: ...


class HybridRetriever:
    def __init__(
        self,
        lexical: LexicalFindingRetriever,
        chunks: ChunkRetriever,
        *,
        rrf_k: int = 60,
        chunk_k: int = 20,
    ) -> None:
        self._lex, self._chunks = lexical, chunks
        self._rrf_k, self._chunk_k = rrf_k, chunk_k

    def retrieve(self, query: str, top_k: int = 8) -> list[Hit]:
        lex_hits = self._lex.retrieve(query, top_k=top_k * 3)
        fused: dict[str, float] = {}
        hit_by_id: dict[str, Hit] = {}
        for rank, h in enumerate(lex_hits):
            fused[h.finding.finding_id] = 1 / (self._rrf_k + rank + 1)
            hit_by_id[h.finding.finding_id] = h

        for rank, ch in enumerate(self._chunks.retrieve_chunks(query, self._chunk_k)):
            for f in self._lex.findings:
                s = f.span
                if s.doc_id == ch.doc_id and ch.start <= s.start and s.end <= ch.end:
                    fused[f.finding_id] = fused.get(f.finding_id, 0.0) + 1 / (self._rrf_k + rank + 1)
                    if f.finding_id not in hit_by_id:
                        scored = self._lex.score_finding(query, f.finding_id)
                        if scored is not None:
                            hit_by_id[f.finding_id] = scored

        out = []
        for fid, score in sorted(fused.items(), key=lambda kv: (-kv[1], kv[0])):
            if fid in hit_by_id:
                h = hit_by_id[fid]
                out.append(Hit(h.finding, score, h.coverage, h.missing_terms, h.missing_rare))
        return out[:top_k]
