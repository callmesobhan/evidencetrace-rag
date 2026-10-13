"""Evaluation on the real M1 corpus (PMC open-access RCTs): extraction, provenance, attribution.

Everything is computed per paper first, so confidence intervals come from a *cluster bootstrap over
papers* - findings inside one paper are far from independent (same authors, same phrasing, same
reporting template), and resampling findings would give falsely narrow intervals.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from statistics import fmean
from types import SimpleNamespace
from typing import Any

from evidencetrace.config import Config
from evidencetrace.evaluation.gold import GoldFinding, load_gold_findings
from evidencetrace.evaluation.metrics import match_findings, span_overlap_ok, token_f1
from evidencetrace.extraction.extractor import extract_findings, make_tagger
from evidencetrace.ingest.document import Document
from evidencetrace.ingest.parsers import parse_file
from evidencetrace.schemas import Attribution, Finding, Metric
from evidencetrace.verification.provenance import Verifier

FIELDS = ("intervention", "comparator", "outcome", "population")

# Out-of-scope estimate types, tallied from the near-miss audit so the scope limit is a number, not a vibe.
OUT_OF_SCOPE = {
    "regression_coefficient": r"coefficient|\bβ\b|slope|aCoeff|uCoeff",
    "relative_risk_reduction": r"\bRRR\b|relative risk reduction",
    "incidence_rate": r"incidence rate|\bIR:|per 100 person|per 1000 person",
    "win_ratio": r"win ratio",
    "median_difference": r"median difference",
    "geometric_mean_ratio": r"geometric mean",
    "auc": r"area under the curve|\bAUC\b",
    "non_english": r"\b(?:IC ?95%|razão|diferença)\b",
}
_METRIC_WORD = re.compile(
    r"hazard ratio|odds ratio|risk ratio|relative risk|rate ratio|mean difference|difference|"
    r"\b(?:aHR|HR|OR|aOR|AOR|RR|aRR|SMD|MD|WMD|IRR|RD|aRD)\b",
    re.I,
)
_CI_CUE = re.compile(r"95\s?%|\bCIs?\b|confidence interval")


def manifest(raw: Path) -> list[dict]:
    return [json.loads(ln) for ln in (raw / "manifest.jsonl").read_text().splitlines() if ln.strip()]


def split_ids(raw: Path, split: str) -> list[str]:
    return sorted(r["pmcid"] for r in manifest(raw) if r["split"] == split)


def load_split(raw: Path, split: str) -> dict[str, Document]:
    return {pid: parse_file(raw / f"{pid}.xml") for pid in split_ids(raw, split)}


# ------------------------------------------------------------------------------------ bootstrap
def cluster_bootstrap(
    clusters: list[dict[str, float]],
    stat: Callable[[list[dict[str, float]]], float | None],
    *,
    reps: int = 2000,
    seed: int = 7,
) -> tuple[float | None, float | None, float | None]:
    """(point, lo95, hi95) of ``stat`` with clusters (papers) resampled with replacement."""
    point = stat(clusters)
    if not clusters or point is None:
        return point, None, None
    rng = random.Random(seed)
    draws = []
    for _ in range(reps):
        v = stat([clusters[rng.randrange(len(clusters))] for _ in clusters])
        if v is not None:
            draws.append(v)
    draws.sort()
    if not draws:
        return point, None, None
    return point, draws[int(0.025 * len(draws))], draws[min(len(draws) - 1, int(0.975 * len(draws)))]


def _ratio(num: str, den: Callable[[list[dict]], float]) -> Callable[[list[dict]], float | None]:
    def f(cs: list[dict]) -> float | None:
        d = den(cs)
        return sum(c[num] for c in cs) / d if d else None

    return f


def _f1(cs: list[dict]) -> float | None:
    tp, fp, fn = (sum(c[k] for c in cs) for k in ("tp", "fp", "fn"))
    return 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None


# ------------------------------------------------------------------------------------ evaluation
def _as_pred(row: dict) -> SimpleNamespace:
    """Adapter so saved candidate rows (e.g. the baseline snapshot) can be scored like live Findings."""
    ci = SimpleNamespace(low=row["ci"][0], high=row["ci"][1]) if row.get("ci") else None
    return SimpleNamespace(
        finding_id=row["cand_id"], doc_id=row["doc_id"], metric=Metric(row["metric"]), value=row["value"],
        ci=ci, attribution=Attribution(row["attribution"]),
    )


def score_matching(
    pred: list[Any], gold: list[GoldFinding], doc_ids: list[str], *, ignore_ci: bool = False
) -> tuple[list[dict[str, float]], dict[str, str]]:
    mapping = match_findings(pred, gold, ignore_ci=ignore_ci)
    clusters = []
    for d in doc_ids:
        p_d = [p for p in pred if p.doc_id == d]
        g_d = [g for g in gold if g.doc_id == d]
        tp = sum(p.finding_id in mapping for p in p_d)
        clusters.append({"tp": tp, "fp": len(p_d) - tp, "fn": len(g_d) - tp})
    return clusters, mapping


def prf_ci(clusters: list[dict[str, float]], reps: int = 2000) -> dict[str, Any]:
    prec = _ratio("tp", lambda cs: sum(c["tp"] + c["fp"] for c in cs))
    rec = _ratio("tp", lambda cs: sum(c["tp"] + c["fn"] for c in cs))
    return {
        "precision": cluster_bootstrap(clusters, prec, reps=reps),
        "recall": cluster_bootstrap(clusters, rec, reps=reps),
        "f1": cluster_bootstrap(clusters, _f1, reps=reps),
        "counts": {k: int(sum(c[k] for c in clusters)) for k in ("tp", "fp", "fn")},
    }


def eval_extraction_split(
    docs: dict[str, Document],
    pred: list[Finding],
    gold: list[GoldFinding],
    cfg: Config,
    *,
    reps: int = 2000,
) -> dict[str, Any]:
    doc_ids = sorted(docs)
    clusters, mapping = score_matching(pred, gold, doc_ids)
    relaxed, _ = score_matching(pred, gold, doc_ids, ignore_ci=True)
    by_gold = {g.gold_id: g for g in gold}
    matched = [(p, by_gold[mapping[p.finding_id]]) for p in pred if p.finding_id in mapping]

    # attribution: the dangerous error is another paper's number reported as this paper's own
    own_pred = [p for p in pred if p.attribution is Attribution.OWN]
    own_ok = [p for p in own_pred if p.finding_id in mapping and by_gold[mapping[p.finding_id]].attribution is Attribution.OWN]
    leaked = [p for p in own_pred if p.finding_id in mapping and by_gold[mapping[p.finding_id]].attribution is Attribution.CITED]
    cited_pred = [p for p in pred if p.attribution is Attribution.CITED]
    wrongly_cited = [p for p in cited_pred if p.finding_id in mapping and by_gold[mapping[p.finding_id]].attribution is Attribution.OWN]

    attr_clusters = []
    for d in doc_ids:
        own_d = [p for p in own_pred if p.doc_id == d]
        attr_clusters.append({
            "own_pred": len(own_d),
            "leaked": sum(p in leaked for p in own_d),
            "own_correct": sum(p in own_ok for p in own_d),
        })

    verifier = Verifier(docs, cfg.verification)
    ver = [verifier.verify(p).ok for p in pred]
    attributed = [span_overlap_ok(p.span, g) for p, g in matched]
    annotated = [(p, g) for p, g in matched if g.fields_annotated]

    def acc(pairs: list[bool]) -> float | None:
        return fmean(pairs) if pairs else None

    p_ok = [(p.p_value == g.p_value and p.p_operator == g.p_operator) for p, g in matched]
    n_ok = [p.n == g.n for p, g in matched]
    return {
        "papers": len(doc_ids),
        "predicted": len(pred),
        "gold": len(gold),
        "value_and_ci": prf_ci(clusters, reps),
        "value_only": prf_ci(relaxed, reps),
        "attribution": {
            "leak_rate_own_labelled_but_cited": cluster_bootstrap(
                attr_clusters, _ratio("leaked", lambda cs: sum(c["own_pred"] for c in cs)), reps=reps
            ),
            "own_precision": cluster_bootstrap(
                attr_clusters, _ratio("own_correct", lambda cs: sum(c["own_pred"] for c in cs)), reps=reps
            ),
            "counts": {"predicted_own": len(own_pred), "own_that_are_cited_in_gold": len(leaked),
                       "predicted_cited": len(cited_pred), "cited_that_are_own_in_gold": len(wrongly_cited)},
            "accuracy_on_matched": acc([p.attribution == g.attribution for p, g in matched]),
        },
        "p_value_accuracy_on_matched": acc(p_ok),
        "n_accuracy_on_matched": acc(n_ok),
        "verification_pass_rate": acc(ver),
        "span_attribution_accuracy": acc(attributed),
        "fields": {
            "annotated_pairs": len(annotated),
            **{f: acc([token_f1(getattr(p, f), getattr(g, f)) for p, g in annotated
                       if getattr(p, f) is not None or getattr(g, f) is not None]) for f in FIELDS},  # None/None is not agreement
            "fields_extracted_rate": acc([any(getattr(p, f) for f in FIELDS) for p in pred]),
        },
        "by_metric": {
            m: dict(Counter(g.metric.value for g in gold))[m] for m in sorted({g.metric.value for g in gold})
        },
        "missed_gold": sorted(g.gold_id for g in gold if g.gold_id not in set(mapping.values())),
        "spurious_pred": sorted(p.finding_id for p in pred if p.finding_id not in mapping),
        "_mapping": mapping,
    }


def nearmiss_scope(rows: list[dict]) -> dict[str, Any]:
    """Tally near-miss sentences by *why* they are not (supported) findings."""
    tally: Counter[str] = Counter()
    for r in rows:
        s = r["sentence"]
        cat = next((k for k, pat in OUT_OF_SCOPE.items() if re.search(pat, s, re.I)), None)
        if cat:
            tally[cat] += 1
        elif _CI_CUE.search(s) and re.search(r"\d", s) and not _METRIC_WORD.search(s):
            tally["unnamed_estimate_with_ci"] += 1
        elif _CI_CUE.search(s) and _METRIC_WORD.search(s) and re.search(r"\d", s):
            tally["needs_manual_look_(audited)"] += 1
        else:
            tally["no_effect_estimate"] += 1
    return {"near_miss_sentences": len(rows), **dict(sorted(tally.items()))}


def run_split(
    raw: Path,
    split: str,
    annotation: Path,
    gold_dir: Path,
    cfg: Config | None = None,
    *,
    reps: int = 2000,
) -> dict[str, Any]:
    cfg = cfg or Config()
    docs = load_split(raw, split)
    gold = load_gold_findings(gold_dir / f"{split}_gold_findings.jsonl", docs)
    tagger = make_tagger(cfg.extraction)
    pred = [f for d in docs.values() for f in extract_findings(d, tagger)]
    report = {"split": split, **eval_extraction_split(docs, pred, gold, cfg, reps=reps)}
    nm = annotation / f"{split}_nearmiss.jsonl"
    if nm.exists():
        report["scope"] = nearmiss_scope([json.loads(ln) for ln in nm.read_text().splitlines() if ln.strip()])
    # baseline snapshot (first extractor, before any fix), if one was saved
    v1 = annotation / "v1" / f"{split}_candidates_v1.jsonl"
    if v1.exists():
        rows = [json.loads(ln) for ln in v1.read_text().splitlines() if ln.strip()]
        clusters, _ = score_matching([_as_pred(r) for r in rows], gold, sorted(docs))
        report["baseline_v1"] = {"predicted": len(rows), **prf_ci(clusters, reps)}
    return report


def fmt_ci(t: tuple[float | None, float | None, float | None] | None) -> str:
    if not t or t[0] is None:
        return "n/a"
    lo, hi = ("?" if t[1] is None else f"{t[1]:.3f}"), ("?" if t[2] is None else f"{t[2]:.3f}")
    return f"{t[0]:.3f} [{lo}, {hi}]"


def split_markdown(r: dict[str, Any]) -> str:
    a, v = r["attribution"], r["value_and_ci"]
    rows = [
        f"### `{r['split']}` split - {r['papers']} papers, {r['gold']} gold findings, {r['predicted']} predicted",
        "",
        "| metric | value (95% cluster-bootstrap CI over papers) |",
        "|---|---|",
        f"| value+CI precision | {fmt_ci(v['precision'])} |",
        f"| value+CI recall | {fmt_ci(v['recall'])} |",
        f"| value+CI F1 | {fmt_ci(v['f1'])} |",
        f"| value-only recall (ignores CI) | {fmt_ci(r['value_only']['recall'])} |",
        f"| value-only precision (ignores CI) | {fmt_ci(r['value_only']['precision'])} |",
        f"| **own-labelled results that are really cited ('leak')** | {fmt_ci(a['leak_rate_own_labelled_but_cited'])} |",
        f"| precision of 'own' labels | {fmt_ci(a['own_precision'])} |",
        f"| p-value accuracy (matched) | {r['p_value_accuracy_on_matched']:.3f} |",
        f"| n accuracy (matched) | {r['n_accuracy_on_matched']:.3f} |",
        f"| provenance verification pass rate | {r['verification_pass_rate']:.3f} |",
        f"| span attribution accuracy (matched) | {r['span_attribution_accuracy']:.3f} |",
    ]
    f = r["fields"]
    rows.append(f"| field token-F1 on {f['annotated_pairs']} annotated matched pairs (int / cmp / out / pop) | "
                + " / ".join("n/a" if f[k] is None else f"{f[k]:.2f}" for k in FIELDS) + " |")
    if "baseline_v1" in r:
        b = r["baseline_v1"]
        rows.append(f"| *baseline extractor before fixes*: P / R / F1 | {fmt_ci(b['precision'])} / {fmt_ci(b['recall'])} / {fmt_ci(b['f1'])} |")
    if "scope" in r:
        rows += ["", "Near-miss audit (sentences that look statistical but yielded no finding):", "",
                 "```", json.dumps(r["scope"], indent=1), "```"]
    return "\n".join(rows)
