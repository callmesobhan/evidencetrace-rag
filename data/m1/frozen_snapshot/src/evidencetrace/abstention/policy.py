"""When to refuse.

The policy is a pure function over the funnel the pipeline already computed, so every abstention
carries machine-readable reasons and the thresholds live in config, not code.

Funnel:  hits -> relevant (coverage) -> verified (provenance) -> confident (extractor) -> answer
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evidencetrace.config import AbstentionConfig
from evidencetrace.schemas import AbstainReason, AnswerStatus, Conflict


@dataclass
class Decision:
    status: AnswerStatus
    reasons: list[AbstainReason] = field(default_factory=list)


def decide(
    *,
    n_hits: int,
    n_relevant: int,
    n_verified: int,
    n_confident: int,
    conflicts: list[Conflict],
    cfg: AbstentionConfig,
) -> Decision:
    def abstain(reason: AbstainReason) -> Decision:
        return Decision(AnswerStatus.ABSTAINED, [reason])

    if n_hits == 0:
        return abstain(AbstainReason.NO_RELEVANT_FINDINGS)
    if n_relevant == 0:
        return abstain(AbstainReason.LOW_COVERAGE)
    if n_verified == 0:
        return abstain(AbstainReason.UNVERIFIED_PROVENANCE)
    if n_confident == 0:
        return abstain(AbstainReason.LOW_CONFIDENCE)
    if n_confident < cfg.min_verified:
        return abstain(AbstainReason.INSUFFICIENT_SUPPORT)
    if conflicts:
        if cfg.conflict_mode == "abstain":
            return abstain(AbstainReason.UNRESOLVED_CONFLICT)
        return Decision(AnswerStatus.CONFLICTING)
    return Decision(AnswerStatus.ANSWERED)


REASON_TEXT = {
    AbstainReason.NO_RELEVANT_FINDINGS: "no quantitative finding in the corpus matches the query",
    AbstainReason.LOW_COVERAGE: "related findings exist, but none covers the specific "
    "intervention/outcome/population asked about",
    AbstainReason.UNVERIFIED_PROVENANCE: "candidate findings could not be verified against the "
    "source text",
    AbstainReason.LOW_CONFIDENCE: "candidate findings were extracted with low confidence",
    AbstainReason.INSUFFICIENT_SUPPORT: "not enough independent verified findings",
    AbstainReason.UNRESOLVED_CONFLICT: "verified findings conflict and the policy is set to abstain",
}
