"""Corrected accuracy from a human's adjudication decisions.

    python -I scripts/apply_adjudication.py --decisions adjudication_decisions.jsonl --out OUT [--scores DIR ...]

``--decisions`` is the file the page docs/adjudication.html exports. Reports the system's precision / recall / F1 as
scored, and as corrected by the verdicts under three policies for "unsure" (see evaluation/adjudication.py).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrace.evaluation.adjudication import load_decisions, report
from evidencetrace.evaluation.m1 import fmt_ci

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", type=Path, required=True)
    ap.add_argument("--scores", type=Path, action="append",
                    help="dir with independent_scores.json + disagreements.jsonl (repeatable; default: both rounds of the frozen pre-fix "
                         "system, data/m1/independent/scores_prefix_strict and holdout2/scores_prefix_system)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args()
    dirs = args.scores or [ROOT / "data/m1/independent/scores_prefix_strict", ROOT / "data/m1/independent/holdout2/scores_prefix_system"]
    per_paper, dis = [], []
    for d in dirs:
        scores = json.loads((d / "independent_scores.json").read_text())
        per_paper += scores["system_vs_independent"]["all_fresh"]["per_paper"]
        dis += [json.loads(ln) for ln in (d / "disagreements.jsonl").read_text().splitlines() if ln.strip()]
    rep = report(per_paper, dis, load_decisions(args.decisions), args.reps)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "adjudicated.json").write_text(json.dumps(rep, indent=1) + "\n")
    lines = ["| | precision | recall | F1 |", "|---|---|---|---|"]
    for name, r in [("as scored (annotator = truth)", rep["as_scored"]), *[(f"adjudicated, unsure -> {k}", v) for k, v in rep["adjudicated"].items()]]:
        lines.append(f"| {name} | {fmt_ci(r['precision'])} | {fmt_ci(r['recall'])} | {fmt_ci(r['f1'])} |")
    t = rep["tally"]
    lines += ["", f"system-only items: {t['system_only']}", f"annotator-only items: {t['annotator_only']}"]
    (args.out / "adjudicated.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
