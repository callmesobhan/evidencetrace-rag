"""Gold annotation formats.

Gold findings store a *quote* (a distinctive substring of the paper), not offsets, so annotators
never have to count characters and gold survives re-canonicalisation. Offsets are resolved at load
time; if a quote is missing from its paper the loader fails loudly rather than scoring against air.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from evidencetrace.ingest.document import Document
from evidencetrace.schemas import Attribution, Metric


class GoldFinding(BaseModel):
    gold_id: str
    doc_id: str
    quote: str
    metric: Metric
    value: float
    ci: tuple[float, float] | None = None
    p_value: float | None = None
    p_operator: str | None = None
    n: int | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    population: str | None = None
    attribution: Attribution = Attribution.OWN
    # Intervention/comparator/outcome/population are only annotated for a subset (expensive); field
    # metrics are computed over those. Value/CI/p/n/attribution are annotated for every finding.
    fields_annotated: bool = False
    note: str | None = None
    # resolved at load time
    start: int = -1
    end: int = -1


class GoldQuery(BaseModel):
    qid: str
    query: str
    expected_status: Literal["answered", "conflicting", "abstained"]
    gold_findings: list[str] = []
    gold_conflicts: list[tuple[str, str, str]] = []  # (gold_id_a, gold_id_b, kind)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def load_gold_findings(path: Path, docs: dict[str, Document]) -> list[GoldFinding]:
    out = []
    for row in _jsonl(path):
        g = GoldFinding.model_validate(row)
        doc = docs.get(g.doc_id)
        if doc is None:
            raise ValueError(f"gold {g.gold_id}: unknown doc {g.doc_id!r}")
        starts = [i for i in range(len(doc.text)) if doc.text.startswith(g.quote, i)]
        if not starts:
            raise ValueError(f"gold {g.gold_id}: quote not found in {g.doc_id}: {g.quote!r}")
        # a result duplicated in the abstract is gold in the Results copy
        in_results = [s for s in starts if doc.section_at(s) == "results"]
        g.start = (in_results or starts)[0]
        g.end = g.start + len(g.quote)
        out.append(g)
    return out


def load_gold_queries(path: Path) -> list[GoldQuery]:
    return [GoldQuery.model_validate(r) for r in _jsonl(path)]
