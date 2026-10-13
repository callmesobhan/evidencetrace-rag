"""Score the system against an INDEPENDENT annotation, and measure agreement with the developer's gold.

    python -I scripts/score_blind.py --pack PACK --map blind_map.json --preds predictions.jsonl \\
        --test-gold data/m1/gold/test_gold_findings.jsonl --manifest data/raw/fresh/manifest.jsonl --out OUT

PACK/out/annotations_*.jsonl are written by annotators who never saw the system's output. Papers in the
map with kind == "agreement" are existing TEST-split papers: there the independent annotation is compared
with the developer's gold (inter-annotator agreement). Papers with kind == "fresh" were never seen during
development: there the *frozen* system's predictions are scored against the independent annotation.

Everything is computed per paper first and bootstrapped over papers.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from evidencetrace.evaluation.gold import GoldFinding
from evidencetrace.evaluation.m1 import fmt_ci, prf_ci, score_matching
from evidencetrace.schemas import Attribution, Metric

MERGE: dict[str, str] = {}  # set by --lenient-metrics: {"IRR": "RR"}


def _m(name: str) -> Metric:
    return Metric(MERGE.get(name, name))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _gold(records: list[dict], prefix: str) -> list[GoldFinding]:
    out = []
    for i, r in enumerate(records, 1):
        ci = None if r.get("ci_inconsistent") or not r.get("ci") else tuple(r["ci"])
        out.append(GoldFinding(
            gold_id=f"{prefix}-{i:04d}", doc_id=r["doc_id"], quote=r.get("quote") or "x", metric=_m(r["metric"]),
            value=float(r["value"]), ci=ci, p_value=r.get("p_value"), p_operator=r.get("p_operator"),
            attribution=Attribution(r["attribution"]),
        ))
    return out


def _pred(rows: list[dict]) -> list[SimpleNamespace]:
    # Matching is keyed by finding_id, and files written by the frozen extractor contain duplicate ids (its id ignored
    # the interval), so key by row instead: the row number makes every prediction distinct.
    return [SimpleNamespace(
        finding_id=f"{r['finding_id']}#{i}", doc_id=r["pmcid"], metric=_m(r["metric"]), value=r["value"],
        ci=SimpleNamespace(low=r["ci"][0], high=r["ci"][1]) if r["ci"] else None,
        attribution=Attribution(r["attribution"]), sentence=r["quote_sentence"],
    ) for i, r in enumerate(rows)]


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", type=Path, required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--preds", type=Path, required=True)
    ap.add_argument("--test-gold", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True, help="fresh manifest (domain = query prefix)")
    ap.add_argument("--chosen", type=Path, help="JSON list of pack ids that were actually assigned")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--lenient-metrics", action="store_true", help="treat IRR and RR as the same metric (rate-ratio naming is a taxonomy choice)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.lenient_metrics:
        MERGE.update({"IRR": "RR"})

    mp = json.loads(args.map.read_text())
    chosen = set(json.loads(args.chosen.read_text())) if args.chosen else set(mp)
    pid2pmc = {p: m["pmcid"] for p, m in mp.items() if p in chosen}
    kind = {m["pmcid"]: m["kind"] for p, m in mp.items() if p in chosen}
    domain = {}
    for ln in args.manifest.read_text().splitlines():
        if ln.strip():
            r = json.loads(ln)
            domain[r["pmcid"]] = "cardiometabolic" if r["query"].startswith("(hypertension") else "other"

    # Accept a record only from the annotator ASSIGNED that paper: a crashed earlier run can leave stale
    # records in another annotator's file, and merging them would double-count a paper.
    ann, oos, dropped = [], [], []
    for glob, sink in (("annotations_*.jsonl", ann), ("out_of_scope_*.jsonl", oos)):
        for f in sorted((args.pack / "out").glob(glob)):
            k = f.stem.rsplit("_", 1)[1]
            assigned = set((args.pack / f"assignment_{k}.txt").read_text().split()) if (args.pack / f"assignment_{k}.txt").exists() else set()
            for r in _jsonl(f):
                (sink if r["doc_id"] in assigned else dropped).append(r)
    stray = Counter(r["doc_id"] for r in dropped)
    ann = [{**r, "doc_id": pid2pmc[r["doc_id"]]} for r in ann if r["doc_id"] in pid2pmc]
    oos = [{**r, "doc_id": pid2pmc[r["doc_id"]]} for r in oos if r["doc_id"] in pid2pmc]
    annotated_docs = sorted({r["doc_id"] for r in ann})
    missing = sorted(set(pid2pmc.values()) - set(annotated_docs))

    report: dict = {"papers_assigned": len(pid2pmc), "papers_with_annotations": len(annotated_docs),
                    "papers_without_any_annotation": missing, "in_scope_records": len(ann),
                    "out_of_scope_records": dict(Counter(r["category"] for r in oos)),
                    "uncertain_flagged": sum(bool(r.get("uncertain")) for r in ann),
                    "stale_records_dropped_not_assigned": dict(stray)}

    # ---------------------------------------------------------------- agreement with the developer's gold
    agree_docs = sorted(d for d in kind if kind[d] == "agreement")
    mine = [g for g in (GoldFinding.model_validate(r) for r in _jsonl(args.test_gold)) if g.doc_id in agree_docs]
    theirs = _gold([r for r in ann if r["doc_id"] in agree_docs], "ind")
    pred_like = [SimpleNamespace(finding_id=g.gold_id, doc_id=g.doc_id, metric=g.metric, value=g.value,
                                 ci=SimpleNamespace(low=g.ci[0], high=g.ci[1]) if g.ci else None,
                                 attribution=g.attribution) for g in theirs]
    clusters, mapping = score_matching(pred_like, mine, agree_docs)
    by_mine = {g.gold_id: g for g in mine}
    by_their = {g.gold_id: g for g in theirs}
    attr_pairs = [(by_their[t].attribution.value, by_mine[m].attribution.value) for t, m in mapping.items()]
    report["agreement_with_developer_gold"] = {
        "papers": len(agree_docs), "developer_gold": len(mine), "independent": len(theirs),
        "independent_vs_developer": prf_ci(clusters, args.reps),
        "attribution_agreement_on_matched": (sum(a == b for a, b in attr_pairs) / len(attr_pairs)) if attr_pairs else None,
        "attribution_kappa": cohen_kappa(attr_pairs),
        "only_independent": [f"{by_their[g.gold_id].doc_id} {g.metric.value} {g.value} {g.ci}" for g in theirs if g.gold_id not in mapping],
        "only_developer": [f"{g.doc_id} {g.metric.value} {g.value} {g.ci}" for g in mine if g.gold_id not in set(mapping.values())],
    }

    # ---------------------------------------------------------------- frozen system vs independent annotation
    fresh_docs = sorted(d for d in kind if kind[d] == "fresh")
    preds_all = _pred(_jsonl(args.preds))
    gold_fresh = _gold([r for r in ann if r["doc_id"] in fresh_docs], "fresh")
    preds_fresh = [p for p in preds_all if p.doc_id in fresh_docs]

    def score(docs: list[str]) -> dict:
        g = [x for x in gold_fresh if x.doc_id in docs]
        p = [x for x in preds_fresh if x.doc_id in docs]
        cl, mp_ = score_matching(p, g, docs)
        clr, _ = score_matching(p, g, docs, ignore_ci=True)
        gi = {x.gold_id: x for x in g}
        own_p = [x for x in p if x.attribution is Attribution.OWN]
        leaked = [x for x in own_p if x.finding_id in mp_ and gi[mp_[x.finding_id]].attribution is Attribution.CITED]
        cited_p = [x for x in p if x.attribution is Attribution.CITED]
        wrong = [x for x in cited_p if x.finding_id in mp_ and gi[mp_[x.finding_id]].attribution is Attribution.OWN]
        per_paper = [{"pmcid": d, "gold": c["tp"] + c["fn"], "pred": c["tp"] + c["fp"], "tp": c["tp"]} for d, c in zip(docs, cl, strict=True)]
        return {"per_paper": per_paper, "papers": len(docs), "independent_gold": len(g), "system_predictions": len(p),
                "value_and_ci": prf_ci(cl, args.reps), "value_only": prf_ci(clr, args.reps),
                "own_labels": len(own_p), "own_that_independent_calls_cited": len(leaked),
                "cited_labels": len(cited_p), "cited_that_independent_calls_own": len(wrong),
                "attribution_kappa_on_matched": cohen_kappa([(x.attribution.value, gi[mp_[x.finding_id]].attribution.value) for x in p if x.finding_id in mp_])}

    report["system_vs_independent"] = {
        "all_fresh": score(fresh_docs),
        "cardiometabolic": score([d for d in fresh_docs if domain.get(d) == "cardiometabolic"]),
        "other_domains": score([d for d in fresh_docs if domain.get(d) == "other"]),
    }

    # ---------------------------------------------------------------- disagreement lists for adjudication
    _, mp_all = score_matching(preds_fresh, gold_fresh, fresh_docs)
    used = set(mp_all.values())
    lines = []
    for p in preds_fresh:
        if p.finding_id not in mp_all:
            lines.append({"type": "system_only", "pmcid": p.doc_id, "metric": p.metric.value, "value": p.value,
                          "ci": [p.ci.low, p.ci.high] if p.ci else None, "attribution": p.attribution.value,
                          "sentence": p.sentence})
    quotes = {(r["doc_id"], r["metric"], r["value"]): r for r in ann}
    for g in gold_fresh:
        if g.gold_id not in used:
            r = quotes.get((g.doc_id, g.metric.value, g.value), {})
            lines.append({"type": "annotator_only", "pmcid": g.doc_id, "metric": g.metric.value, "value": g.value,
                          "ci": list(g.ci) if g.ci else None, "attribution": g.attribution.value, "sentence": r.get("quote")})
    (args.out / "disagreements.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n")
    (args.out / "independent_scores.json").write_text(json.dumps(report, indent=1, default=str))

    a = report["agreement_with_developer_gold"]
    s = report["system_vs_independent"]["all_fresh"]
    print(f"annotated {report['papers_with_annotations']}/{report['papers_assigned']} papers; "
          f"{report['in_scope_records']} in-scope, {sum(report['out_of_scope_records'].values())} out-of-scope records")
    print(f"AGREEMENT on {a['papers']} overlap papers  independent-vs-developer F1 {fmt_ci(a['independent_vs_developer']['f1'])}  "
          f"attribution kappa {a['attribution_kappa']}")
    print(f"SYSTEM vs INDEPENDENT on {s['papers']} fresh papers  P {fmt_ci(s['value_and_ci']['precision'])}  "
          f"R {fmt_ci(s['value_and_ci']['recall'])}  F1 {fmt_ci(s['value_and_ci']['f1'])}")
    print(f"  own labels that independent calls cited: {s['own_that_independent_calls_cited']}/{s['own_labels']}; "
          f"disagreements written: {len(lines)}")


if __name__ == "__main__":
    main()
