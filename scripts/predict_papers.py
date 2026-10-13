"""Run the extractor over the blind-annotation papers and write one JSONL row per predicted finding.

    python -I scripts/predict_papers.py --map data/m1/independent/pack/blind_map.json \\
        --raw-fresh data/raw/fresh --raw-main data/raw/pmc --out predictions.jsonl [--config configs/posthoc.toml]

The output is what scripts/score_blind.py scores. To regenerate the *pre-fix, held-out* file recorded in
data/m1/FROZEN.json run this with the source in data/m1/frozen_snapshot_fresh (see data/m1/independent/README.md).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrace.config import Config
from evidencetrace.extraction.extractor import extract_findings, make_tagger
from evidencetrace.ingest.parsers import parse_file


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True, help="blind_map.json: opaque id -> {pmcid, kind}")
    ap.add_argument("--raw-fresh", type=Path, required=True)
    ap.add_argument("--raw-main", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--only", type=Path, default=None, help="JSON list of opaque ids to predict (default: all in the map)")
    args = ap.parse_args()
    cfg = Config.load(args.config)
    tagger = make_tagger(cfg.extraction)
    mp = json.loads(args.map.read_text())
    if args.only:
        keep = set(json.loads(args.only.read_text()))
        mp = {k: v for k, v in mp.items() if k in keep}
    rows = []
    for pid in sorted(mp):
        pmcid, kind = mp[pid]["pmcid"], mp[pid]["kind"]
        raw = args.raw_fresh if kind == "fresh" else args.raw_main
        for f in extract_findings(parse_file(raw / f"{pmcid}.xml"), tagger):
            rows.append({"pmcid": pmcid, "pid": pid, "kind": kind, "finding_id": f.finding_id, "metric": f.metric.value,
                         "value": f.value, "ci": [f.ci.low, f.ci.high] if f.ci else None, "p_value": f.p_value,
                         "p_operator": f.p_operator, "attribution": f.attribution.value,
                         "section": f.span.section, "quote_sentence": f.span.text, "confidence": f.confidence})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} predictions over {len(mp)} papers -> {args.out}")


if __name__ == "__main__":
    main()
