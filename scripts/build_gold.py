"""Merge frozen candidate sheets + reviewer decisions into a gold file.

    python -I scripts/build_gold.py --split dev --annotation data/m1/annotation \
        --raw data/raw/pmc --out data/m1/gold

Reviewer decisions live in <annotation>/<split>_review.json:

  rejected     [{match, reason}]            candidate is not a valid finding (precision error)
  corrections  [{match, set:{...}}]         fix a field the system got wrong (e.g. attribution, ci)
  fields       [{match, intervention, comparator, outcome, population}]   field-annotated subset
  missed       [{doc_id, quote, metric, value, ci, p_value, p_operator, n, attribution, note}]
                                            true estimates the system did not extract (recall error)

``match`` selects exactly ONE candidate by any of: doc_id, metric, value, ci, section, contains
(substring of the sentence). Zero or several matches abort the build - decisions never silently
apply to the wrong row.

The reviewer is a single annotator (an LLM, not a human): see docs/m1-report.md for what that does
and does not license.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrace.evaluation.gold import GoldFinding, load_gold_findings
from evidencetrace.ingest.parsers import parse_file


def select(rows: list[dict], match: dict) -> dict:
    hits = [
        r for r in rows
        if all(
            (k == "contains" and match[k] in r["sentence"])
            or (k == "ci" and r["ci"] is not None and [round(x, 6) for x in r["ci"]] == match[k])
            or (k == "value" and abs(r["value"] - match[k]) < 1e-9)
            or (k not in {"contains", "ci", "value"} and r.get(k) == match[k])
            for k in match
        )
    ]
    if len(hits) != 1:
        raise SystemExit(f"selector {match} matched {len(hits)} candidates (need exactly 1)")
    return hits[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--annotation", type=Path, required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    cands = [json.loads(ln) for ln in (args.annotation / f"{args.split}_candidates.jsonl").read_text().splitlines() if ln]
    review = json.loads((args.annotation / f"{args.split}_review.json").read_text())

    rejected = {select(cands, d["match"])["cand_id"] for d in review.get("rejected", [])}
    for d in review.get("corrections", []):
        select(cands, d["match"]).update(d["set"])
    for d in review.get("fields", []):
        row = select(cands, d["match"])
        row.update({k: d.get(k) for k in ("intervention", "comparator", "outcome", "population")})
        row["fields_annotated"] = True

    gold: list[dict] = []
    for r in cands:
        if r["cand_id"] in rejected:
            continue
        gold.append({
            "gold_id": f"{args.split}-g{len(gold) + 1:04d}", "doc_id": r["doc_id"], "quote": r["quote"],
            "metric": r["metric"], "value": r["value"], "ci": r["ci"], "p_value": r["p_value"],
            "p_operator": r["p_operator"], "n": r["n"], "intervention": r["intervention"] if r.get("fields_annotated") else None,
            "comparator": r["comparator"] if r.get("fields_annotated") else None,
            "outcome": r["outcome"] if r.get("fields_annotated") else None,
            "population": r["population"] if r.get("fields_annotated") else None,
            "attribution": r["attribution"], "fields_annotated": bool(r.get("fields_annotated")),
            "note": r.get("note"),
        })
    n_from_candidates = len(gold)
    for m in review.get("missed", []):
        gold.append({"gold_id": f"{args.split}-g{len(gold) + 1:04d}", "attribution": "own", "fields_annotated": False, **m})

    docs = {}
    for g in gold:
        if g["doc_id"] not in docs:
            docs[g["doc_id"]] = parse_file(args.raw / f"{g['doc_id']}.xml")
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.split}_gold_findings.jsonl"
    path.write_text("\n".join(json.dumps(g, ensure_ascii=False) for g in gold) + "\n", encoding="utf-8")
    load_gold_findings(path, docs)  # fails loudly if any quote is not in its paper

    meta = {
        "split": args.split, "papers": len({g["doc_id"] for g in gold}), "gold_findings": len(gold),
        "from_candidates": n_from_candidates, "rejected": len(rejected), "added_missed": len(review.get("missed", [])),
        "corrections": len(review.get("corrections", [])), "field_annotated": sum(g["fields_annotated"] for g in gold),
        "reviewer": review.get("reviewer"),
    }
    (args.out / f"{args.split}_gold_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    # keep the validated model import used (GoldFinding) honest
    assert GoldFinding.model_fields


if __name__ == "__main__":
    main()
