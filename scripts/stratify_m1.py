"""Extraction metrics split by study design (confirmed trials vs everything else).

    python -I scripts/stratify_m1.py --raw data/raw/pmc --m1 data/m1 --out OUT [--config configs/posthoc.toml]

Reads data/m1/design.jsonl (see scripts/fetch_design.py). Same matching and cluster bootstrap over papers as run_m1.py;
the strata are small, so read the intervals, not the point estimates. Run with the current code: on the test split the
current and frozen extractors differ only by the covariate-balance SMD filter (see docs/m1-report.md).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrace.config import Config
from evidencetrace.evaluation.gold import load_gold_findings
from evidencetrace.evaluation.m1 import fmt_ci, load_split, prf_ci, score_matching
from evidencetrace.evaluation.metrics import match_findings
from evidencetrace.extraction.extractor import extract_findings, make_tagger
from evidencetrace.schemas import Attribution

GROUPS = {
    "all papers": lambda d: True,
    "confirmed trials": lambda d: d == "trial",
    "not confirmed as trials": lambda d: d != "trial",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--m1", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args()
    cfg = Config.load(args.config)
    tagger = make_tagger(cfg.extraction)
    design = {r["pmcid"]: r["design"] for r in map(json.loads, (args.m1 / "design.jsonl").read_text().splitlines())}
    args.out.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    for split in ("dev", "test"):
        docs = load_split(args.raw, split)
        gold = load_gold_findings(args.m1 / "gold" / f"{split}_gold_findings.jsonl", docs)
        pred = [f for d in docs.values() for f in extract_findings(d, tagger)]
        ids = sorted(docs)
        mapping = match_findings(pred, gold)
        gold_by_id = {g.gold_id: g for g in gold}
        report[split] = {}
        for name, keep in GROUPS.items():
            sel = [d for d in ids if keep(design[d])]
            p = [x for x in pred if x.doc_id in sel]
            g = [x for x in gold if x.doc_id in sel]
            clusters, _ = score_matching(p, g, sel)
            own = [x for x in p if x.attribution is Attribution.OWN]
            leaked = [x for x in own if x.finding_id in mapping and gold_by_id[mapping[x.finding_id]].attribution is Attribution.CITED]
            report[split][name] = {"papers": len(sel), "gold": len(g), "predicted": len(p), **prf_ci(clusters, args.reps),
                                   "own_labels": len(own), "own_that_are_cited": len(leaked),
                                   "designs": {k: sum(1 for d in sel if design[d] == k) for k in sorted({design[d] for d in sel})}}
    (args.out / "by_design.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    lines = ["| split | group | papers | gold | precision | recall | F1 | own labels that are cited |", "|---|---|---|---|---|---|---|---|"]
    for split, groups in report.items():
        for name, r in groups.items():
            lines.append(f"| {split} | {name} | {r['papers']} | {r['gold']} | {fmt_ci(r['precision'])} | {fmt_ci(r['recall'])} | "
                         f"{fmt_ci(r['f1'])} | {r['own_that_are_cited']} / {r['own_labels']} |")
    (args.out / "by_design.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
