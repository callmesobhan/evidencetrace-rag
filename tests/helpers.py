"""Test factories. Findings built here are *synthetic* and not tied to any document text."""

from __future__ import annotations

from evidencetrace.schemas import (
    Attribution,
    Finding,
    Interval,
    Metric,
    SourceSpan,
    make_finding_id,
)


def make_finding(
    *,
    doc_id: str = "doc1",
    metric: Metric = Metric.MD,
    value: float = -5.0,
    ci: tuple[float, float] | None = (-7.0, -3.0),
    p: float | None = None,
    p_op: str | None = None,
    intervention: str | None = "Drug Zeta",
    comparator: str | None = "placebo",
    outcome: str | None = "systolic blood pressure",
    population: str | None = None,
    attribution: Attribution = Attribution.OWN,
    confidence: float = 0.9,
    start: int = 0,
) -> Finding:
    text = f"{intervention} changed {outcome} ({metric.value} {value})."
    return Finding(
        finding_id=make_finding_id(doc_id, start, start + len(text), metric, value),
        doc_id=doc_id,
        doc_sha256="x",
        metric=metric,
        value=value,
        ci=Interval(low=ci[0], high=ci[1], level=95) if ci else None,
        p_value=p,
        p_operator=p_op,  # type: ignore[arg-type]
        intervention=intervention,
        comparator=comparator,
        outcome=outcome,
        population=population,
        attribution=attribution,
        span=SourceSpan(doc_id=doc_id, start=start, end=start + len(text), text=text,
                        section="results"),
        extractor="test",
        confidence=confidence,
    )
