"""Results of the scope-rule re-judgement: agreement on the re-judged items, and the holdout F1 under the adopted rules.

    python -I scripts/rules_round_result.py --first decisions.jsonl --second decisions_second.jsonl \\
        --rules-owner decisions_rules_owner.jsonl --rules-second decisions_rules_second.jsonl --out OUT

The 14 items on PMC12703296 and PMC12117457 are re-judged under guidelines v1.2. Every other item keeps the verdict the two
adjudicators already agreed on (the script refuses to run if they did not agree). Each adjudicator's F1 is computed with their own
re-judgement; the agreement between the two re-judgements is reported with Cohen's kappa.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrace.evaluation.adjudication import (
    adjudicate,
    cohen_kappa,
    compare_adjudicators,
    load_decisions,
)
from evidencetrace.evaluation.m1 import fmt_ci, prf_ci

ROOT = Path(__file__).resolve().parent.parent
RULE_PAPERS = {"PMC12703296", "PMC12117457"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=Path, required=True, help="the owner's original verdicts (decisions.jsonl)")
    ap.add_argument("--second", type=Path, required=True, help="the second adjudicator's original verdicts (decisions_second.jsonl)")
    ap.add_argument("--rules-owner", type=Path, required=True)
    ap.add_argument("--rules-second", type=Path, required=True)
    ap.add_argument("--scores", type=Path, default=ROOT / "data/m1/independent/holdout2/scores_prefix_system")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args()
    first, second = load_decisions(args.first), load_decisions(args.second)
    r_owner, r_second = load_decisions(args.rules_owner), load_decisions(args.rules_second)
    common = set(first) & set(second)
    per_paper = json.loads((args.scores / "independent_scores.json").read_text())["system_vs_independent"]["all_fresh"]["per_paper"]
    dis = [json.loads(ln) for ln in (args.scores / "disagreements.jsonl").read_text().splitlines() if ln.strip()]

    rule_ids = {i for i in common if second[i]["pmcid"] in RULE_PAPERS}
    base = {}
    for i in common - rule_ids:
        if first[i]["decision"] != second[i]["decision"]:
            raise SystemExit(f"item {i} is not a rule item but the two original verdicts differ; resolve it first")
        base[i] = first[i]
    if len(rule_ids) != 14:
        raise SystemExit(f"expected 14 rule items, found {len(rule_ids)}")
    for name, dec in (("owner", r_owner), ("second", r_second)):
        missing = rule_ids - set(dec)
        if missing:
            raise SystemExit(f"{name} re-judgement is missing {len(missing)} item(s)")
    rows = {
        "original verdicts, owner (check: 0.839)": adjudicate(per_paper, dis, first, "exclude"),
        "original verdicts, second (check: 0.848)": adjudicate(per_paper, dis, second, "exclude"),
        "adopted rules, owner": adjudicate(per_paper, dis, {**base, **{i: r_owner[i] for i in rule_ids}}, "exclude"),
        "adopted rules, second": adjudicate(per_paper, dis, {**base, **{i: r_second[i] for i in rule_ids}}, "exclude"),
    }
    figures = {k: prf_ci(v, args.reps) for k, v in rows.items()}
    figures["as scored (annotator = truth)"] = prf_ci(adjudicate(per_paper, dis, {}, "exclude"), args.reps)
    rc = compare_adjudicators({i: r_owner[i] for i in rule_ids}, {i: r_second[i] for i in rule_ids})
    kappa = cohen_kappa([(r_owner[i]["decision"], r_second[i]["decision"]) for i in sorted(rule_ids)])
    unsure = sum(1 for d in list(r_owner.values()) + list(r_second.values()) if d["decision"] == "unk")
    by_item = [{"id": i, "pmcid": second[i]["pmcid"], "original_owner": first[i]["decision"], "original_second": second[i]["decision"],
                "rules_owner": r_owner[i]["decision"], "rules_second": r_second[i]["decision"],
                "owner_note": r_owner[i].get("note"), "second_note": r_second[i].get("note")} for i in sorted(rule_ids)]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "rules_round.json").write_text(json.dumps({"agreement": {k: v for k, v in rc.items() if k != "common_ids"},
                                                          "kappa": kappa, "unsure": unsure, "figures": figures, "items": by_item}, indent=1) + "\n")
    lines = [f"re-judged items: {len(rule_ids)}   raw agreement: {rc['raw_agreement']:.3f}   Cohen's kappa: "
             + (f"{kappa:.3f}" if kappa is not None else "n/a") + f"   unsure: {unsure}",
             f"confusion (owner -> second): {rc['confusion']}", "",
             "| verdicts used | precision | recall | F1 |", "|---|---|---|---|"]
    lines += [f"| {k} | {fmt_ci(v['precision'])} | {fmt_ci(v['recall'])} | {fmt_ci(v['f1'])} |" for k, v in figures.items()]
    (args.out / "rules_round.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
