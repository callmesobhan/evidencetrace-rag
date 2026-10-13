"""Write the hard-negative query set for one split (queries whose words all occur together but whose answer is "abstain").

    python -I scripts/make_hardneg_queries.py --split dev --raw data/raw/pmc --gold data/m1/gold --out data/m1/queries

Deterministic: derived from the gold file alone. See ``build_hard_negatives`` for the one family it builds and why
(real annotations contain no sentence with two different interventions, so within-sentence role swaps cannot be mined;
they live in the labelled synthetic set data/samples_hardneg instead).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrace.evaluation.gold import load_gold_findings
from evidencetrace.evaluation.m1 import load_split
from evidencetrace.evaluation.m1_queries import build_hard_negatives


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    docs = load_split(args.raw, args.split)
    gold = load_gold_findings(args.gold / f"{args.split}_gold_findings.jsonl", docs)
    queries = build_hard_negatives(gold, split=args.split)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.split}_hardneg_queries.jsonl"
    path.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queries), encoding="utf-8")
    print(f"wrote {len(queries)} hard-negative queries -> {path}")


if __name__ == "__main__":
    main()
