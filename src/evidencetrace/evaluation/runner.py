"""End-to-end evaluation: ingest a corpus, answer gold queries, score every stage separately.

Scoring each stage on its own is the point: an end-to-end accuracy number cannot tell you whether a
wrong answer came from extraction, attribution, conflict logic, or the abstention threshold.
"""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from evidencetrace.config import Config
from evidencetrace.evaluation.gold import (
    GoldFinding,
    GoldQuery,
    load_gold_findings,
    load_gold_queries,
)
from evidencetrace.evaluation.metrics import (
    aurc,
    match_findings,
    prf,
    risk_coverage,
    span_overlap_ok,
    token_f1,
)
from evidencetrace.pipeline import EvidencePipeline
from evidencetrace.schemas import Answer, AnswerStatus, Finding
from evidencetrace.verification.provenance import Verifier

FIELDS = ("intervention", "comparator", "outcome", "population")


def run_evaluation(corpus: Path, gold_dir: Path, cfg: Config | None = None) -> dict[str, Any]:
    cfg = cfg or Config()
    with tempfile.TemporaryDirectory() as tmp:
        pipe = EvidencePipeline(Path(tmp) / "ws", cfg)
        pipe.ingest_paths([corpus])
        docs = pipe.ws.load_documents()
        findings = pipe.ws.load_findings()
        gold_f = load_gold_findings(gold_dir / "gold_findings.jsonl", docs)
        gold_q = load_gold_queries(gold_dir / "gold_queries.jsonl")

        mapping = match_findings(findings, gold_f)
        verifier = Verifier(docs, cfg.verification)
        report: dict[str, Any] = {
            "extraction": eval_extraction(findings, gold_f, mapping),
            "provenance": eval_provenance(findings, gold_f, mapping, verifier),
        }
        answers = [(q, pipe.ask(q.query)) for q in gold_q]
    report.update(eval_queries(answers, mapping))
    report["config"] = {
        "tagger": cfg.extraction.tagger,
        "backend": cfg.retrieval.backend,
        "min_coverage": cfg.abstention.min_coverage,
        "min_confidence": cfg.abstention.min_confidence,
        "conflict_mode": cfg.abstention.conflict_mode,
    }
    report["sizes"] = {"papers": len(docs), "gold_findings": len(gold_f), "queries": len(gold_q)}
    return report


# ---------------------------------------------------------------- stage: extraction
def eval_extraction(
    pred: list[Finding], gold: list[GoldFinding], mapping: dict[str, str]
) -> dict[str, Any]:
    by_id = {g.gold_id: g for g in gold}
    tp = len(mapping)
    out: dict[str, Any] = {"value_ci": prf(tp, len(pred) - tp, len(gold) - tp)}

    matched = [(p, by_id[mapping[p.finding_id]]) for p in pred if p.finding_id in mapping]

    def acc(pairs: list[bool]) -> float | None:
        return fmean(pairs) if pairs else None

    out["p_value_acc"] = acc([
        (p.p_value == g.p_value and p.p_operator == g.p_operator) for p, g in matched
    ])
    out["n_acc"] = acc([p.n == g.n for p, g in matched])
    out["attribution_acc"] = acc([p.attribution == g.attribution for p, g in matched])
    out["field_token_f1"] = {
        f: acc([token_f1(getattr(p, f), getattr(g, f)) for p, g in matched]) for f in FIELDS
    }
    out["missed"] = sorted(set(by_id) - set(mapping.values()))
    out["spurious"] = sorted(p.finding_id for p in pred if p.finding_id not in mapping)
    return out


# ---------------------------------------------------------------- stage: provenance
def eval_provenance(
    pred: list[Finding],
    gold: list[GoldFinding],
    mapping: dict[str, str],
    verifier: Verifier,
) -> dict[str, Any]:
    by_id = {g.gold_id: g for g in gold}
    results = [verifier.verify(f) for f in pred]
    failing: dict[str, int] = defaultdict(int)
    for r in results:
        for name in r.failures:
            failing[name] += 1
    attributed = [
        span_overlap_ok(p.span, by_id[mapping[p.finding_id]]) for p in pred if p.finding_id in mapping
    ]
    return {
        "verification_pass_rate": fmean(r.ok for r in results) if results else None,
        "failed_checks": dict(failing),
        "span_attribution_acc": fmean(attributed) if attributed else None,
    }


# ---------------------------------------------------------------- stage: queries
def _conflict_keys(answer: Answer, mapping: dict[str, str]) -> set[tuple[frozenset[str], str]]:
    keys = set()
    for c in answer.conflicts:
        a = mapping.get(c.finding_a, f"?{c.finding_a}")
        b = mapping.get(c.finding_b, f"?{c.finding_b}")
        keys.add((frozenset({a, b}), c.kind.value))
    return keys


def eval_queries(
    answers: list[tuple[GoldQuery, Answer]], mapping: dict[str, str]
) -> dict[str, Any]:
    per_query, rc_items = [], []
    c_tp = c_fp = c_fn = 0
    kinds: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # tp, fp, fn per conflict kind

    for q, ans in answers:
        answerable = q.expected_status != "abstained"
        shown = ans.findings or ans.nearest_evidence  # what the user would see
        pred_set = {mapping.get(f.finding_id, f"?{f.finding_id}") for f in shown}
        set_correct = answerable and pred_set == set(q.gold_findings)
        # Risk-coverage is over the queries the system answered; an unanswerable query is wrong whenever the
        # system produces anything, and a correct abstention is not an error (it only lowers coverage).
        if ans.status is not AnswerStatus.ABSTAINED:
            rc_items.append((ans.confidence, set_correct))

        pred_c = _conflict_keys(ans, mapping)
        gold_c = {(frozenset({a, b}), k) for a, b, k in q.gold_conflicts}
        c_tp, c_fp, c_fn = c_tp + len(pred_c & gold_c), c_fp + len(pred_c - gold_c), c_fn + len(gold_c - pred_c)
        for _, k in pred_c & gold_c:
            kinds[k][0] += 1
        for _, k in pred_c - gold_c:
            kinds[k][1] += 1
        for _, k in gold_c - pred_c:
            kinds[k][2] += 1

        per_query.append({
            "qid": q.qid,
            "expected": q.expected_status,
            "predicted": ans.status.value,
            "status_ok": ans.status.value == q.expected_status,
            "set_correct": set_correct if ans.status is not AnswerStatus.ABSTAINED else None,
            "confidence": ans.confidence,
            "abstain_reasons": [r.value for r in ans.abstain_reasons],
            "missing_conflicts": sorted(f"{sorted(k[0])}:{k[1]}" for k in gold_c - pred_c),
            "spurious_conflicts": sorted(f"{sorted(k[0])}:{k[1]}" for k in pred_c - gold_c),
        })

    unans = [r for r in per_query if r["expected"] == "abstained"]
    ans_ok = [r for r in per_query if r["expected"] != "abstained"]
    abstained = [r for r in per_query if r["predicted"] == "abstained"]
    answered = [r for r in per_query if r["predicted"] != "abstained"]
    abst_tp = sum(r["expected"] == "abstained" for r in abstained)

    abstention = {
        "status_accuracy": fmean(r["status_ok"] for r in per_query),
        "false_answer_rate": (
            sum(r["predicted"] != "abstained" for r in unans) / len(unans) if unans else None
        ),
        "over_abstention_rate": (
            sum(r["predicted"] == "abstained" for r in ans_ok) / len(ans_ok) if ans_ok else None
        ),
        "abstain": prf(abst_tp, len(abstained) - abst_tp, len(unans) - abst_tp),
        "coverage": len(answered) / len(per_query) if per_query else None,
        "selective_accuracy": (
            fmean(bool(r["set_correct"]) for r in answered) if answered else None
        ),
    }
    return {
        "abstention": abstention,
        "conflicts": {
            "overall": prf(c_tp, c_fp, c_fn),
            "by_kind": {k: prf(*v) for k, v in sorted(kinds.items())},
        },
        "risk_coverage": {
            "aurc": aurc(rc_items),
            "curve": [(round(c, 3), round(r, 3)) for c, r in risk_coverage(rc_items)],
        },
        "per_query": per_query,
    }


# ---------------------------------------------------------------- reporting
def _f(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def to_markdown(r: dict[str, Any]) -> str:
    e, p, a, c = r["extraction"], r["provenance"], r["abstention"], r["conflicts"]
    lines = [
        "# EvidenceTrace-RAG evaluation",
        "",
        f"corpus: {r['sizes']['papers']} papers, {r['sizes']['gold_findings']} gold findings, "
        f"{r['sizes']['queries']} queries - config: {json.dumps(r['config'])}",
        "",
        "| stage | metric | value |",
        "|---|---|---|",
        f"| extraction | value+CI precision / recall / F1 | {_f(e['value_ci']['precision'])} / "
        f"{_f(e['value_ci']['recall'])} / {_f(e['value_ci']['f1'])} |",
        f"| extraction | p-value accuracy (matched) | {_f(e['p_value_acc'])} |",
        f"| extraction | attribution own/cited accuracy | {_f(e['attribution_acc'])} |",
        *[
            f"| extraction | field token-F1: {k} | {_f(v)} |"
            for k, v in e["field_token_f1"].items()
        ],
        f"| provenance | verification pass rate | {_f(p['verification_pass_rate'])} |",
        f"| provenance | span attribution accuracy | {_f(p['span_attribution_acc'])} |",
        f"| conflicts | P / R / F1 | {_f(c['overall']['precision'])} / {_f(c['overall']['recall'])} / "
        f"{_f(c['overall']['f1'])} |",
        *[
            f"| conflicts | F1 ({k}) | {_f(v['f1'])} |" for k, v in c["by_kind"].items()
        ],
        f"| abstention | status accuracy (3-way) | {_f(a['status_accuracy'])} |",
        f"| abstention | false-answer rate (answered when it should abstain) | {_f(a['false_answer_rate'])} |",
        f"| abstention | over-abstention rate (abstained when answerable) | {_f(a['over_abstention_rate'])} |",
        f"| abstention | coverage / selective accuracy | {_f(a['coverage'])} / {_f(a['selective_accuracy'])} |",
        f"| abstention | AURC (lower is better) | {_f(r['risk_coverage']['aurc'])} |",
        "",
        "## Per query",
        "",
        "| qid | expected | predicted | ok | reasons |",
        "|---|---|---|---|---|",
        *[
            f"| {q['qid']} | {q['expected']} | {q['predicted']} | {'yes' if q['status_ok'] else '**NO**'} "
            f"| {', '.join(q['abstain_reasons'])} |"
            for q in r["per_query"]
        ],
        "",
        "> Smoke-test numbers on a tiny synthetic corpus. They show the harness works and the stages "
        "are wired correctly; they are not evidence of real-world accuracy. See docs/evaluation.md.",
    ]
    if e["missed"] or e["spurious"]:
        lines += ["", f"missed gold findings: {e['missed']}  spurious predictions: {e['spurious']}"]
    return "\n".join(lines)


def write_reports(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / "eval.json", out_dir / "eval.md"
    jp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    mp.write_text(to_markdown(report), encoding="utf-8")
    return jp, mp
