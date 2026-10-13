"""Conflict detection between findings that answer the same question.

Two findings are *comparable* when they come from different papers, share a metric family
(ratio vs difference), and agree on intervention / outcome (/ comparator when both give one).
Ratios are compared on the log scale so that HR 0.5 and HR 2.0 are symmetric around the null.

Kinds (checked in this order):
  DIRECTION    both significant, effects on opposite sides of the null          -> high
  MAGNITUDE    same metric, confidence intervals do not overlap                  -> medium
  SIGNIFICANCE CIs overlap, but exactly one excludes the null                    -> low
"""

from __future__ import annotations

import math
from itertools import combinations

from evidencetrace.config import ConflictConfig
from evidencetrace.schemas import Conflict, ConflictKind, Finding, Metric
from evidencetrace.textnorm import jaccard, tokenize


def _scaled(f: Finding) -> tuple[float, float | None, float | None] | None:
    """(point, low, high) on the scale where the null is 0. None if not representable."""
    if f.metric.is_ratio:
        vals = [f.value] + ([f.ci.low, f.ci.high] if f.ci else [])
        if any(v <= 0 for v in vals):
            return None
        point = math.log(f.value)
        return (point, math.log(f.ci.low), math.log(f.ci.high)) if f.ci else (point, None, None)
    return (f.value, f.ci.low, f.ci.high) if f.ci else (f.value, None, None)


def _significant(f: Finding, cfg: ConflictConfig) -> bool | None:
    s = _scaled(f)
    if s is None:
        return None
    _, lo, hi = s
    if lo is not None and hi is not None:
        return lo > 0 or hi < 0
    if f.p_value is not None:
        if f.p_operator in {"<", "<="}:
            return f.p_value <= cfg.alpha  # "p<0.05" is significant at alpha = 0.05
        if f.p_operator == "=":
            return f.p_value < cfg.alpha
        if f.p_operator in {">", ">="}:
            return False if f.p_value >= cfg.alpha else None  # "p>0.001" says nothing
    return None


def _same_names(a: str | None, b: str | None, cfg: ConflictConfig, *, required: bool) -> bool:
    if not a or not b:
        return not required
    return jaccard(tokenize(a), tokenize(b)) >= cfg.min_name_overlap


def _same_scale(a: Finding, b: Finding) -> bool:
    """Differences are only comparable on one scale: a mean difference in mmHg is not an SMD, nor a difference in kPa."""
    if {a.metric, b.metric} == {Metric.MD, Metric.SMD}:
        return False
    ua, ub = (a.unit or "").lower().replace(" ", ""), (b.unit or "").lower().replace(" ", "")
    return not (ua and ub and ua != ub)


def comparable(a: Finding, b: Finding, cfg: ConflictConfig) -> bool:
    if a.doc_id == b.doc_id or a.metric.family != b.metric.family or not _same_scale(a, b):
        return False
    req = cfg.require_intervention_and_outcome
    if not _same_names(a.intervention, b.intervention, cfg, required=req):
        return False
    if not _same_names(a.outcome, b.outcome, cfg, required=req):
        return False
    # comparators: only enforce when both papers state one
    return _same_names(a.comparator, b.comparator, cfg, required=False)


def unassessed_pairs(findings: list[Finding], cfg: ConflictConfig | None = None) -> int:
    """Pairs that *might* conflict but can't be checked because intervention/outcome is missing.

    Without this, a failed field tagger would turn conflict detection off silently and two
    contradictory findings would be reported as a plain, confident answer.
    """
    cfg = cfg or ConflictConfig()
    if not cfg.require_intervention_and_outcome:
        return 0
    n = 0
    for a, b in combinations(findings, 2):
        if a.doc_id == b.doc_id or a.metric.family != b.metric.family or not _same_scale(a, b):
            continue
        if not (a.intervention and a.outcome and b.intervention and b.outcome):
            n += 1
    return n


def _describe(f: Finding) -> str:
    return f"{f.doc_id} reports {f.brief()}"


def detect_conflicts(findings: list[Finding], cfg: ConflictConfig | None = None) -> list[Conflict]:
    cfg = cfg or ConflictConfig()
    conflicts: list[Conflict] = []
    for a, b in combinations(findings, 2):
        if not comparable(a, b, cfg):
            continue
        sa, sb = _scaled(a), _scaled(b)
        if sa is None or sb is None:
            continue
        sig_a, sig_b = _significant(a, cfg), _significant(b, cfg)
        topic = f"{a.intervention or '?'} / {a.outcome or '?'}"
        pair = f"{_describe(a)}; {_describe(b)}"
        note = ""
        if a.population and b.population and jaccard(tokenize(a.population), tokenize(b.population)) < 0.5:
            note = " Populations differ, so this may reflect effect modification rather than disagreement."

        kind: ConflictKind | None = None
        if sig_a and sig_b and (sa[0] > 0) != (sb[0] > 0):
            kind, sev = ConflictKind.DIRECTION, "high"
            why = "significant effects point in opposite directions"
        elif (
            a.metric == b.metric
            and None not in (sa[1], sa[2], sb[1], sb[2])
            and (sa[2] < sb[1] or sb[2] < sa[1])  # type: ignore[operator]
        ):
            kind, sev = ConflictKind.MAGNITUDE, "medium"
            why = "confidence intervals do not overlap"
        elif sig_a is not None and sig_b is not None and sig_a != sig_b:
            kind, sev = ConflictKind.SIGNIFICANCE, "low"
            why = "only one confidence interval excludes the null"
        if kind is not None:
            conflicts.append(
                Conflict(
                    kind=kind,
                    finding_a=a.finding_id,
                    finding_b=b.finding_id,
                    severity=sev,
                    explanation=f"{topic}: {why}. {pair}.{note}",
                )
            )
    return conflicts
