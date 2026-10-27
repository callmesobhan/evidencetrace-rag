"""Compare a fresh PubMed design lookup with the committed data/m1/design.jsonl (the second half of `make design`).

    python -I scripts/check_design.py reports/design.jsonl data/m1/design.jsonl

Fails if any paper's classification (design, basis, disagree, pmid, split) changed, or a paper appeared or disappeared. A change to
PubMed's publication types that leaves every classification as it was is printed and accepted: the results read only the committed
classification, and PubMed keeps indexing records after publication. See data/m1/drift_log.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidencetrace.ingest.design import compare_design


def _rows(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("current", type=Path, help="the fresh lookup (scripts/fetch_design.py --out ...)")
    ap.add_argument("committed", type=Path, help="data/m1/design.jsonl")
    args = ap.parse_args()
    if args.current.read_bytes() == args.committed.read_bytes():
        print(f"design: identical to {args.committed}")
        return 0
    diff = compare_design(_rows(args.current), _rows(args.committed))
    bad = [f"  missing from the lookup: {p}" for p in diff["missing"]] + [f"  not in the committed record: {p}" for p in diff["added"]]
    bad += [f"  classification changed: {c['pmcid']} {c['fields']}" for c in diff["classification"]]
    if bad:
        print("design: the classification changed; the committed results no longer match PubMed", file=sys.stderr)
        print("\n".join(bad), file=sys.stderr)
        return 1
    print(f"design: classification identical for all {len(_rows(args.committed))} papers; PubMed's publication types changed for "
          f"{len(diff['types_only'])} (accepted, see data/m1/drift_log.md):")
    for t in diff["types_only"]:
        print(f"  {t['pmcid']}: added {t['added']} removed {t['removed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
