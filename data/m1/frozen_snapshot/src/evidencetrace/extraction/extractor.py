"""Document -> list[Finding]: numeric candidates + field tags + attribution + dedupe."""

from __future__ import annotations

import re

from evidencetrace.abbreviations import aliases_for
from evidencetrace.config import ExtractionConfig
from evidencetrace.extraction.candidates import find_effect_candidates
from evidencetrace.extraction.fields import FieldTagger, RuleFieldTagger
from evidencetrace.ingest.document import Document
from evidencetrace.ingest.sentences import split_sentences
from evidencetrace.schemas import (
    Attribution,
    Finding,
    Interval,
    SourceSpan,
    make_finding_id,
)

_CITATION = re.compile(
    r"\[\d+(?:\s*[,–-]\s*\d+)*\]"                                # [3] [1,2] [4-6]
    r"|\([A-Z][A-Za-z-]+(?:\s+et\s+al\.?|\s+and\s+[A-Z][a-z]+),?\s+\d{4}\)"  # (Smith et al., 2020)
    r"|\bet\s+al\b"
)
# Which copy of a duplicated result (abstract + results) to keep.
_SECTION_RANK = {"results": 0, "abstract": 1, "conclusion": 2, "discussion": 3}


# In Discussion/Conclusion most numbers belong to other studies, so "own" must be positively signalled.
_OWN_CUE = re.compile(
    r"\b(?:our|we|us|this (?:study|trial|analysis|cohort|work|paper|meta-analysis|review)|"
    r"(?:present|current) (?:study|trial|analysis|work|cohort)|these (?:results|findings))\b",
    re.IGNORECASE,
)


def detect_attribution(sentence: str, section: str) -> Attribution:
    """Heuristic: a result in the introduction, next to a citation marker, or in a discussion
    sentence that never says "our/we/this study" is someone else's.

    Conservative by design. It sometimes mislabels an author's own number as cited (e.g. a
    meta-analysis' pooled result printed beside citations of the included trials); the cost is an
    abstention, not a wrong answer. The reverse error - another study's number labelled "own" - is
    the one that matters, and the Discussion rule exists to shrink it.
    """
    if section == "introduction" or _CITATION.search(sentence):
        return Attribution.CITED
    if section in {"discussion", "conclusion"} and not _OWN_CUE.search(sentence):
        return Attribution.CITED
    return Attribution.OWN


def make_tagger(cfg: ExtractionConfig) -> FieldTagger:
    if cfg.tagger == "rules":
        return RuleFieldTagger()
    if cfg.tagger == "bert":
        from evidencetrace.extraction.bert_tagger import BertFieldTagger

        return BertFieldTagger(cfg.bert_model)
    raise ValueError(f"unknown tagger {cfg.tagger!r}")


def extract_findings(
    doc: Document, tagger: FieldTagger | None = None, *, dedupe_findings: bool = True
) -> list[Finding]:
    tagger = tagger or RuleFieldTagger()
    findings: list[Finding] = []
    for sent in split_sentences(doc):
        candidates = find_effect_candidates(sent.text, sent.start)
        if not candidates:
            continue
        fields = tagger.tag(sent.text)
        attribution = detect_attribution(sent.text, sent.section)
        span = SourceSpan(
            doc_id=doc.doc_id, start=sent.start, end=sent.end, text=sent.text, section=sent.section
        )
        for c in candidates:
            if sent.section == "methods" and c.ci_low is None and c.p_value is None:
                continue  # "we propose to assess a mean difference of 0.15" is a plan, not a result
            ci = (
                Interval(low=c.ci_low, high=c.ci_high, level=c.ci_level)
                if c.ci_low is not None and c.ci_high is not None
                else None
            )
            findings.append(
                Finding(
                    finding_id=make_finding_id(doc.doc_id, sent.start, sent.end, c.metric, c.value),
                    doc_id=doc.doc_id,
                    doc_sha256=doc.sha256,
                    metric=c.metric,
                    value=c.value,
                    ci=ci,
                    p_value=c.p_value,
                    p_operator=c.p_operator,  # type: ignore[arg-type]
                    n=c.n,
                    unit=c.unit,
                    intervention=fields.intervention,
                    comparator=fields.comparator,
                    outcome=fields.outcome,
                    population=fields.population,
                    attribution=attribution,
                    context=doc.title,
                    aliases=aliases_for(sent.text, doc.abbreviations),
                    span=span,
                    extractor=f"{tagger.name}+regex-v1",
                    confidence=_confidence(ci is not None, c.p_value is not None, fields.confidence,
                                           attribution),
                )
            )
    return dedupe(findings) if dedupe_findings else findings


def _confidence(has_ci: bool, has_p: bool, field_conf: float, attribution: Attribution) -> float:
    """Transparent heuristic, not a calibrated probability (calibration is an eval task)."""
    conf = 0.35 + 0.25 * has_ci + 0.10 * has_p + 0.30 * field_conf
    if attribution is Attribution.CITED:
        conf *= 0.5
    return round(min(conf, 1.0), 4)


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Collapse restatements of one estimate.

    1. Same estimate (incl. CI) in abstract and results: keep one, preferring the Results copy.
    2. Same point estimate restated *without* an interval in the Discussion ("our mean difference of
       0.25% ...") when a copy with an interval exists in the same paper: drop the bare restatement.
    """
    best: dict[tuple, Finding] = {}
    for f in findings:
        ci = (f.ci.low, f.ci.high) if f.ci else None
        key = (f.doc_id, f.metric, f.value, ci)
        rank = _SECTION_RANK.get(f.span.section or "", 9)
        if key not in best or rank < _SECTION_RANK.get(best[key].span.section or "", 9):
            best[key] = f
    with_ci = {(f.doc_id, f.metric, f.value) for f in best.values() if f.ci}
    kept = {
        f.finding_id
        for f in best.values()
        if f.ci or (f.doc_id, f.metric, f.value) not in with_ci
    }
    return [f for f in findings if f.finding_id in kept]
