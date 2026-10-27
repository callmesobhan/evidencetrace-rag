"""Build or restore the M1 corpus: permissively-licensed PMC open-access papers.

Discover new papers (network ranking drifts, so this is NOT reproducible):
    python scripts/fetch_pmc.py --out data/raw/pmc --target 110 --max-ids 320
    python scripts/fetch_pmc.py --out data/raw/fresh --query "<pubmed query>" --split-label fresh \
        --exclude-manifest data/m1/corpus_manifest.jsonl --target 30 --max-ids 900

Pin what was found (exact PMCIDs + SHA-256 of every XML):
    python scripts/fetch_pmc.py --out data/raw/pmc --pin data/m1/corpus_manifest.jsonl

Restore EXACTLY that corpus and verify it (this is the reproducible path):
    python scripts/fetch_pmc.py --out data/raw/pmc --from-manifest data/m1/corpus_manifest.jsonl

Downloads JATS XML (roughly 50-300 KB per paper) from NCBI E-utilities, keeps CC BY / CC0 research articles
only. data/raw/ is git-ignored: papers are re-downloaded, never committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidencetrace.ingest.pmc import fetch_corpus, fetch_pinned, pin_manifest

DEFAULT_QUERY = (
    '(hypertension[tiab] OR "type 2 diabetes"[tiab] OR "heart failure"[tiab]) '
    'AND ("hazard ratio"[tiab] OR "mean difference"[tiab] OR "odds ratio"[tiab] OR "risk ratio"[tiab]) '
    "AND 2019:2026[dp] AND free full text[sb]"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/raw/pmc"))
    ap.add_argument("--query", default=DEFAULT_QUERY, help="PubMed syntax; the RCT clause is added for you")
    ap.add_argument("--target", type=int, default=110, help="stop once this many CC BY/CC0 papers are kept")
    ap.add_argument("--max-ids", type=int, default=320, help="ids to request from PubMed")
    ap.add_argument("--exclude-manifest", type=Path, help="JSONL of PMCIDs that must not be re-fetched")
    ap.add_argument("--split-label", help="override the dev/test hash split (e.g. 'fresh')")
    ap.add_argument("--pin", type=Path, help="write a pinned manifest (with SHA-256) for the papers in --out and exit")
    ap.add_argument("--from-manifest", type=Path, help="download exactly the PMCIDs in this pinned manifest")
    ap.add_argument("--allow-drift", action="store_true", help="keep papers whose article CONTENT changed since pinning")
    ap.add_argument("--canonical-pins", type=Path, default=Path("data/m1/canonical_pins.jsonl"),
                    help="canonical-text pins (see scripts/pin_canonical.py); a record whose text matches is accepted even if PMC's bookkeeping changed")
    args = ap.parse_args()

    if args.pin:
        rows = pin_manifest(args.out)
        args.pin.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print(f"pinned {len(rows)} papers -> {args.pin}")
        return 0

    if args.from_manifest:
        pinned = [json.loads(ln) for ln in args.from_manifest.read_text(encoding="utf-8").splitlines() if ln.strip()]
        canon = {}
        if args.canonical_pins.exists():
            canon = {r["pmcid"]: r["canonical_sha256"] for r in map(json.loads, args.canonical_pins.read_text().splitlines()) if r}
        res = fetch_pinned(pinned, args.out, canonical_pins=canon, allow_drift=args.allow_drift)
        print(f"ok={len(res['ok'])} metadata-only={len(res['metadata'])} drifted={len(res['drifted'])} missing={len(res['missing'])} "
              f"downloaded={len(res['fetched'])}")
        if res["metadata"]:
            print(f"  metadata-only change (article text identical; PMC bookkeeping changed): {', '.join(res['metadata'])}")
        for k in ("drifted", "missing"):
            if res[k]:
                print(f"  {k}: {', '.join(res[k])}", file=sys.stderr)
        return 0 if not (res["drifted"] or res["missing"]) or args.allow_drift else 1

    exclude: set[str] = set()
    if args.exclude_manifest:
        exclude = {json.loads(ln)["pmcid"] for ln in args.exclude_manifest.read_text().splitlines() if ln.strip()}
    rows = fetch_corpus(args.query, args.out, target=args.target, max_ids=args.max_ids, exclude=exclude,
                        split_label=args.split_label)
    dev = sum(r.split == "dev" for r in rows)
    print(f"kept {len(rows)} papers ({dev} dev / {len(rows) - dev} other) in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
