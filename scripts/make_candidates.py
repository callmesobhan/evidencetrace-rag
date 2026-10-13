"""Generate annotation sheets for one split of the M1 corpus.

    python -I scripts/make_candidates.py --raw data/raw/pmc --split dev --out data/m1/annotation

Two files are written (and then FROZEN - review decisions refer to their ids):

  <split>_candidates.jsonl   every finding the current system extracts, pre-filled in gold format.
                             The reviewer accepts, corrects or rejects each one (precision audit).
  <split>_nearmiss.jsonl     sentences with statistical cues that the system extracted NOTHING from.
                             The reviewer marks which hide a reportable effect estimate (recall audit).

Pre-filled predictions anchor reviewers, so precision numbers from this audit are optimistic; the
near-miss file is deliberately independent of predictions and is the honest recall signal.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from evidencetrace.extraction.candidates import find_effect_candidates
from evidencetrace.extraction.extractor import extract_findings
from evidencetrace.ingest.parsers import parse_file
from evidencetrace.ingest.sentences import split_sentences

# A sentence "looks statistical" if it has a digit and any of these cues.
CUE = re.compile(
    r"95\s?%|\bCI\b|confidence interval|hazard ratio|odds ratio|risk ratio|relative risk|"
    r"mean difference|rate ratio|\b(?:aHR|HR|OR|RR|SMD|MD|IRR)\b|\bp\s*[<=>]|\bP\s*[<=>]",
)
NEARMISS_SECTIONS = {"results", "abstract", "conclusion", "discussion", "other"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    manifest = [json.loads(ln) for ln in (args.raw / "manifest.jsonl").read_text().splitlines() if ln]
    pmcids = sorted(r["pmcid"] for r in manifest if r["split"] == args.split)
    args.out.mkdir(parents=True, exist_ok=True)

    cands, misses = [], []
    for pmcid in pmcids:
        doc = parse_file(args.raw / f"{pmcid}.xml")
        findings = extract_findings(doc)
        # coverage is pre-dedupe: an abstract sentence whose estimate was merged into Results is not a miss
        covered = {(f.span.start, f.span.end) for f in extract_findings(doc, dedupe_findings=False)}
        for f in findings:
            c = next(
                (c for c in find_effect_candidates(f.span.text, f.span.start)
                 if c.metric == f.metric and c.value == f.value),
                None,
            )
            cands.append({
                "cand_id": f"{args.split}-c{len(cands) + 1:04d}",
                "doc_id": pmcid,
                "section": f.span.section,
                "sentence": f.span.text,
                "quote": doc.text[c.start : c.end] if c else f.span.text,
                "metric": f.metric.value,
                "value": f.value,
                "ci": [f.ci.low, f.ci.high] if f.ci else None,
                "p_value": f.p_value,
                "p_operator": f.p_operator,
                "n": f.n,
                "intervention": f.intervention,
                "comparator": f.comparator,
                "outcome": f.outcome,
                "population": f.population,
                "attribution": f.attribution.value,
                "confidence": f.confidence,
            })
        for s in split_sentences(doc):
            if (s.start, s.end) in covered or s.section not in NEARMISS_SECTIONS:
                continue
            if CUE.search(s.text) and re.search(r"\d", s.text):
                misses.append({
                    "miss_id": f"{args.split}-m{len(misses) + 1:04d}",
                    "doc_id": pmcid,
                    "section": s.section,
                    "sentence": s.text,
                })

    for name, rows in (("candidates", cands), ("nearmiss", misses)):
        path = args.out / f"{args.split}_{name}.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print(f"{path}: {len(rows)} rows")
    print(f"{len(pmcids)} papers in split '{args.split}'")


if __name__ == "__main__":
    main()
