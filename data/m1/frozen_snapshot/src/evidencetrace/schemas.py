"""Data contracts shared by every stage.

The central object is :class:`Finding`: a structured quantitative result plus the exact
:class:`SourceSpan` it was read from. Everything downstream (verification, conflict
detection, abstention, evaluation) is a function of Findings and the canonical document text.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Metric(StrEnum):
    HR = "HR"      # hazard ratio
    OR = "OR"      # odds ratio
    RR = "RR"      # risk ratio / relative risk
    IRR = "IRR"    # incidence rate ratio
    MD = "MD"      # mean difference
    SMD = "SMD"    # standardised mean difference
    RD = "RD"      # risk difference

    @property
    def is_ratio(self) -> bool:
        return self in {Metric.HR, Metric.OR, Metric.RR, Metric.IRR}

    @property
    def family(self) -> Literal["ratio", "difference"]:
        return "ratio" if self.is_ratio else "difference"


class Attribution(StrEnum):
    OWN = "own"        # the paper reports this result itself
    CITED = "cited"    # the paper is quoting someone else's result


class SourceSpan(BaseModel):
    """A half-open character range ``[start, end)`` into the *canonical* document text."""

    doc_id: str
    start: int
    end: int
    text: str
    section: str | None = None

    @model_validator(mode="after")
    def _check_range(self) -> SourceSpan:
        if not 0 <= self.start < self.end:
            raise ValueError(f"invalid span range [{self.start}, {self.end})")
        return self

    @property
    def citation(self) -> str:
        return f"{self.doc_id}:{self.start}-{self.end}"


class Interval(BaseModel):
    low: float
    high: float
    level: float | None = None   # e.g. 95.0

    @model_validator(mode="after")
    def _check_order(self) -> Interval:
        if self.low > self.high:
            raise ValueError("interval low > high")
        return self


class Finding(BaseModel):
    finding_id: str
    doc_id: str
    doc_sha256: str

    metric: Metric
    value: float
    ci: Interval | None = None
    p_value: float | None = None
    p_operator: Literal["<", "=", ">", "<=", ">="] | None = None
    n: int | None = None
    unit: str | None = None

    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    population: str | None = None

    attribution: Attribution = Attribution.OWN
    # Paper-level context (the title), for display and future use. Deliberately NOT part of
    # ``search_text``: indexing the title made every finding in a paper an answer to any topic in its
    # title (an LDL question was answered with the paper's MI result). Results sentences that don't
    # name the intervention ("the adjusted HR for all-cause mortality was 0.73") are therefore a
    # known recall gap; see docs/m1-report.md.
    context: str | None = None
    # Search-only synonyms from the paper's own abbreviation definitions (GLS <-> global longitudinal strain).
    aliases: list[str] = Field(default_factory=list)
    span: SourceSpan
    extractor: str
    confidence: float = Field(ge=0.0, le=1.0)

    @property
    def search_text(self) -> str:
        parts = [self.intervention, self.comparator, self.outcome, self.population, self.span.text, *self.aliases]
        return " ".join(p for p in parts if p)

    def brief(self) -> str:
        """One-line human rendering of the statistic itself."""
        parts = [f"{self.metric.value} {_fmt(self.value)}"]
        if self.unit:
            parts[0] += f" {self.unit}"
        if self.ci:
            level = f"{_fmt(self.ci.level)}% CI " if self.ci.level else "CI "
            parts.append(f"{level}{_fmt(self.ci.low)} to {_fmt(self.ci.high)}")
        if self.p_value is not None:
            parts.append(f"p{self.p_operator or '='}{_fmt(self.p_value)}")
        if self.n is not None:
            parts.append(f"n={self.n}")
        head, *rest = parts
        return head + (f" ({', '.join(rest)})" if rest else "")


def make_finding_id(doc_id: str, start: int, end: int, metric: Metric, value: float) -> str:
    key = f"{doc_id}|{start}|{end}|{metric.value}|{value!r}"
    return "f_" + hashlib.sha1(key.encode()).hexdigest()[:12]


def _fmt(x: float | None) -> str:
    if x is None:
        return ""
    return f"{x:g}"


class VerificationResult(BaseModel):
    finding_id: str
    checks: dict[str, bool]

    @property
    def ok(self) -> bool:
        return all(self.checks.values())

    @property
    def failures(self) -> list[str]:
        return [k for k, v in self.checks.items() if not v]


class ConflictKind(StrEnum):
    DIRECTION = "direction"        # significant effects in opposite directions
    MAGNITUDE = "magnitude"        # same direction, confidence intervals disjoint
    SIGNIFICANCE = "significance"  # overlapping CIs, but only one excludes the null


class Conflict(BaseModel):
    kind: ConflictKind
    finding_a: str
    finding_b: str
    severity: Literal["high", "medium", "low"]
    explanation: str


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    CONFLICTING = "conflicting"
    ABSTAINED = "abstained"


class AbstainReason(StrEnum):
    NO_RELEVANT_FINDINGS = "no_relevant_findings"
    LOW_COVERAGE = "low_coverage"
    UNVERIFIED_PROVENANCE = "unverified_provenance"
    LOW_CONFIDENCE = "low_confidence"
    INSUFFICIENT_SUPPORT = "insufficient_support"
    UNRESOLVED_CONFLICT = "unresolved_conflict"


class Answer(BaseModel):
    query: str
    status: AnswerStatus
    findings: list[Finding] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    abstain_reasons: list[AbstainReason] = Field(default_factory=list)
    # Closest evidence when abstaining. Shown for transparency; it is NOT an answer.
    nearest_evidence: list[Finding] = Field(default_factory=list)
    # Things the reader must know that are not conflicts, e.g. checks that could not be run.
    caveats: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""
