"""Generate the frozen M1 query set for one split from its gold file.

    python -I scripts/make_queries.py --split dev --raw data/raw/pmc --gold data/m1/gold --out data/m1/queries

Paraphrases are hand-written (data/m1/queries/<split>_paraphrases.json: gold_id -> text) and are
written BEFORE looking at what the system does with them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidencetrace.evaluation.gold import load_gold_findings
from evidencetrace.evaluation.m1 import load_split
from evidencetrace.evaluation.m1_queries import build_queries


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--paraphrases", type=Path, default=None, help="hand-written paraphrases (default: data/m1/queries/<split>_paraphrases.json)")
    args = ap.parse_args()

    docs = load_split(args.raw, args.split)
    gold = load_gold_findings(args.gold / f"{args.split}_gold_findings.jsonl", docs)
    corpus_text = " ".join(
        d.text for d in (load_split(args.raw, "dev") | load_split(args.raw, "test")).values()
    )
    para_path = args.paraphrases or Path(__file__).resolve().parent.parent / "data/m1/queries" / f"{args.split}_paraphrases.json"
    if not para_path.exists():
        sys.exit(f"error: paraphrase file not found: {para_path}\n(pass --paraphrases; without it the query set would silently lose its paraphrase queries and renumber)")
    paraphrases = json.loads(para_path.read_text())
    queries = build_queries(gold, docs, corpus_text, paraphrases, split=args.split)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.split}_queries.jsonl"
    path.write_text("\n".join(json.dumps(q, ensure_ascii=False) for q in queries) + "\n", encoding="utf-8")
    kinds = {k: sum(q["kind"] == k for q in queries) for k in ("annotated", "paraphrase", "cross", "absent")}
    print(f"wrote {len(queries)} queries to {path}: {kinds}")


if __name__ == "__main__":
    main()
