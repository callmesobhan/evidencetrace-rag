"""Agreement between two adjudicators, and what each one's verdicts do to the accuracy figures.

    python -I scripts/adjudication_agreement.py --first data/m1/independent/adjudication/decisions.jsonl \\
        --second adjudication_decisions_second.jsonl --out OUT [--scores data/m1/independent/holdout2/scores_prefix_system]

Compares only the items both decided. Reports raw agreement, Cohen's kappa, the confusion table, every item they disagree on (with
both notes), and the frozen system's precision / recall / F1 on the papers of those items under each adjudicator's verdicts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrace.evaluation.adjudication import adjudicate, compare_adjudicators, item_id, load_decisions
from evidencetrace.evaluation.m1 import fmt_ci, prf_ci

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=Path, required=True)
    ap.add_argument("--second", type=Path, required=True)
    ap.add_argument("--scores", type=Path, default=ROOT / "data/m1/independent/holdout2/scores_prefix_system",
                    help="score directory the second page was built from (independent_scores.json + disagreements.jsonl)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args()
    first, second = load_decisions(args.first), load_decisions(args.second)
    cmp = compare_adjudicators(first, second)
    scores = json.loads((args.scores / "independent_scores.json").read_text())
    per_paper = scores["system_vs_independent"]["all_fresh"]["per_paper"]
    dis = [json.loads(ln) for ln in (args.scores / "disagreements.jsonl").read_text().splitlines() if ln.strip()]
    by_id = {item_id(r): r for r in dis}
    common = set(cmp["common_ids"])
    same_items = {i: d for i, d in first.items() if i in common}, {i: d for i, d in second.items() if i in common}
    figures = {name: prf_ci(adjudicate(per_paper, dis, dec, "exclude"), args.reps)
               for name, dec in (("first adjudicator", same_items[0]), ("second adjudicator", same_items[1]))}
    figures["as scored (annotator = truth)"] = prf_ci(adjudicate(per_paper, dis, {}, "exclude"), args.reps)
    rows = []
    for i in cmp["disagreeing_ids"]:
        r = by_id.get(i, {})
        rows.append({"id": i, "pmcid": r.get("pmcid"), "type": r.get("type"), "metric": r.get("metric"), "value": r.get("value"), "ci": r.get("ci"),
                     "first": first[i]["decision"], "first_note": first[i].get("note"), "second": second[i]["decision"], "second_note": second[i].get("note")})
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "agreement.json").write_text(json.dumps({"agreement": {k: v for k, v in cmp.items() if k != "common_ids"}, "figures": figures, "disagreements": rows}, indent=1) + "\n")
    kappa = cmp["cohen_kappa"]
    lines = [f"items both decided: {cmp['items_both_decided']}   raw agreement: {cmp['raw_agreement']:.3f}   Cohen's kappa: " + (f"{kappa:.3f}" if kappa is not None else "n/a"),
             f"confusion (first->second): {cmp['confusion']}", "", "| verdicts used | precision | recall | F1 |", "|---|---|---|---|"]
    lines += [f"| {k} | {fmt_ci(v['precision'])} | {fmt_ci(v['recall'])} | {fmt_ci(v['f1'])} |" for k, v in figures.items()]
    lines += ["", f"{len(rows)} disagreeing items (both notes in agreement.json)"]
    (args.out / "agreement.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
