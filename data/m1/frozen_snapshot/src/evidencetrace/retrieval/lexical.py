"""Findings-first lexical retrieval with a *coverage* signal.

We retrieve structured Findings (not raw chunks): the unit the user wants is "a quantitative result
about X", and abstention needs to know whether anything in the corpus is about X.

``coverage`` is the share of the query's rarity-weighted terms that a finding contains. Weights are
IDF**2, so a missing rare term ("stroke", "children", "Omega") sinks coverage far more than a missing
ubiquitous one ("drug"). Terms never seen in the corpus get the maximum weight. This is what lets the
pipeline say "the corpus has results about blood pressure, but not about *this*" instead of
returning the nearest topic match.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from evidencetrace.schemas import Finding
from evidencetrace.textnorm import tokenize


@dataclass
class Hit:
    finding: Finding
    score: float
    coverage: float
    missing_terms: list[str] = field(default_factory=list)
    # missing terms that are rare in the corpus: a finding lacking one is about something else
    missing_rare: list[str] = field(default_factory=list)


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 8) -> list[Hit]: ...


class LexicalFindingRetriever:
    def __init__(
        self, findings: list[Finding], *, k1: float = 1.5, b: float = 0.75, rare_fraction: float = 0.10
    ):
        self.findings = findings
        self._rare_fraction = rare_fraction
        self._k1, self._b = k1, b
        self._tokens = [tokenize(f.search_text) for f in findings]
        self._tf = [Counter(t) for t in self._tokens]
        self._len = [len(t) for t in self._tokens]
        self._avg = (sum(self._len) / len(self._len)) if self._len else 0.0
        self._df: Counter[str] = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())
        self._n = len(findings)
        self._idf_max = math.log(1 + (self._n + 0.5) / 0.5)

    def _idf(self, term: str) -> float:
        df = self._df.get(term)
        if df is None:
            return self._idf_max
        return math.log(1 + (self._n - df + 0.5) / (df + 0.5))

    def score_index(self, i: int, terms: list[str]) -> Hit:
        tf, dl = self._tf[i], self._len[i]
        bm25 = 0.0
        for t in set(terms):
            f = tf.get(t, 0)
            if f:
                norm = f + self._k1 * (1 - self._b + self._b * dl / (self._avg or 1))
                bm25 += self._idf(t) * f * (self._k1 + 1) / norm
        weights = {t: self._idf(t) ** 2 for t in set(terms)}
        total = sum(weights.values())
        covered = sum(w for t, w in weights.items() if t in tf)
        missing = sorted(t for t in weights if t not in tf)
        rare = [t for t in missing if self._is_rare(t)]
        return Hit(
            finding=self.findings[i],
            score=bm25,
            coverage=(covered / total) if total else 0.0,
            missing_terms=missing,
            missing_rare=rare,
        )

    def _is_rare(self, term: str) -> bool:
        df = self._df.get(term, 0)
        return df == 0 or df <= self._rare_fraction * self._n

    def score_finding(self, query: str, finding_id: str) -> Hit | None:
        for i, f in enumerate(self.findings):
            if f.finding_id == finding_id:
                return self.score_index(i, tokenize(query))
        return None

    def retrieve(self, query: str, top_k: int = 8) -> list[Hit]:
        terms = tokenize(query)
        if not terms or not self.findings:
            return []
        hits = [self.score_index(i, terms) for i in range(self._n)]
        hits = [h for h in hits if h.score > 0]
        hits.sort(key=lambda h: (-h.score, h.finding.finding_id))
        return hits[:top_k]
