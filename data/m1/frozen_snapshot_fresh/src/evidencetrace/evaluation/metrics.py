"""Metric primitives. Pure functions, no pipeline imports beyond schemas, easy to unit-test."""

from __future__ import annotations

import re

from evidencetrace.evaluation.gold import GoldFinding
from evidencetrace.schemas import Finding, SourceSpan


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    if tp == fp == fn == 0:  # nothing to find, nothing found
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f1}


def token_f1(a: str | None, b: str | None) -> float:
    """Token-overlap F1 between two field strings; None/None counts as a perfect match."""
    if a is None and b is None:
        return 1.0
    if a is None or b is None:
        return 0.0
    ta, tb = re.findall(r"\w+", a.lower()), re.findall(r"\w+", b.lower())
    common = sum(min(ta.count(t), tb.count(t)) for t in set(ta))
    if common == 0:
        return 0.0
    p, r = common / len(ta), common / len(tb)
    return 2 * p * r / (p + r)


def _close(a: float | None, b: float | None, tol: float = 1e-9) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol)


def finding_equals(pred: Finding, gold: GoldFinding, *, ignore_ci: bool = False) -> bool:
    """Same statistic from the same paper: doc, metric, point estimate and CI (if gold has one)."""
    if pred.doc_id != gold.doc_id or pred.metric != gold.metric or not _close(pred.value, gold.value):
        return False
    if gold.ci is not None and not ignore_ci:
        return pred.ci is not None and _close(pred.ci.low, gold.ci[0]) and _close(pred.ci.high, gold.ci[1])
    return True


def match_findings(
    pred: list[Finding], gold: list[GoldFinding], *, ignore_ci: bool = False
) -> dict[str, str]:
    """Greedy one-to-one matching, predicted finding_id -> gold_id."""
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for p in pred:
        for g in gold:
            if g.gold_id not in used and finding_equals(p, g, ignore_ci=ignore_ci):
                mapping[p.finding_id] = g.gold_id
                used.add(g.gold_id)
                break
    return mapping


def span_overlap_ok(span: SourceSpan, gold: GoldFinding, min_iou: float = 0.5) -> bool:
    """Prediction is correctly attributed if its span contains the gold quote, or IoU >= min_iou."""
    if span.start <= gold.start and gold.end <= span.end:
        return True
    inter = max(0, min(span.end, gold.end) - max(span.start, gold.start))
    union = (span.end - span.start) + (gold.end - gold.start) - inter
    return union > 0 and inter / union >= min_iou


def risk_coverage(items: list[tuple[float, bool]]) -> list[tuple[float, float]]:
    """(coverage, risk) points obtained by answering the most-confident items first.

    ``items`` are (confidence, is_correct). Risk is the error rate among answered items.
    """
    ordered = sorted(items, key=lambda x: -x[0])
    points, errors = [], 0
    for k, (_, ok) in enumerate(ordered, 1):
        errors += not ok
        points.append((k / len(ordered), errors / k))
    return points


def aurc(items: list[tuple[float, bool]]) -> float:
    """Area under the risk-coverage curve (lower is better). 0.0 for an empty set."""
    pts = risk_coverage(items)
    return sum(r for _, r in pts) / len(pts) if pts else 0.0
