"""Check the committed study-design record (data/m1/design.jsonl).

    python -I scripts/check_design.py offline                         # make design: recompute from the committed record, no network
    python -I scripts/check_design.py live reports/design.jsonl data/m1/design.jsonl   # make design-live: compare with PubMed today

``offline`` recomputes every classification from the record's own PubMed publication types and the manifests' titles, and checks each
PMID against the paper's own JATS when the papers are downloaded. It gives the same answer every week, so the reproduction does not
depend on what PubMed indexes today.

``live`` compares a fresh PubMed lookup (scripts/fetch_design.py) with the committed record. PubMed keeps indexing records after
publication, so a change in publication types that leaves every classification as it was is printed and accepted. A changed
classification, or a paper that appeared or disappeared, fails: the committed results no longer match PubMed and a person should
decide whether to re-derive them. See data/m1/drift_log.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidencetrace.ingest.design import compare_design, pmid_of, verify_design_record

ROOT = Path(__file__).resolve().parent.parent
M1 = ROOT / "data" / "m1"


def _rows(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def offline() -> int:
    committed = _rows(M1 / "design.jsonl")
    manifests = _rows(M1 / "corpus_manifest.jsonl") + _rows(M1 / "fresh_manifest.jsonl")
    jats: dict[str, str | None] = {}
    for raw in (ROOT / "data/raw/pmc", ROOT / "data/raw/fresh"):
        for r in committed:
            xml = raw / f"{r['pmcid']}.xml"
            if xml.exists():
                jats[r["pmcid"]] = pmid_of(xml.read_text(encoding="utf-8"))
    problems = verify_design_record(committed, manifests, jats)
    if problems:
        print("design: the committed record is inconsistent", file=sys.stderr)
        print("\n".join(f"  {p}" for p in problems), file=sys.stderr)
        return 1
    print(f"design: all {len(committed)} classifications recomputed from the committed PubMed types and titles; "
          f"{len(jats)} PMIDs checked against the papers' own metadata")
    return 0


def live(current: Path, committed: Path) -> int:
    if current.read_bytes() == committed.read_bytes():
        print(f"design-live: identical to {committed}")
        return 0
    diff = compare_design(_rows(current), _rows(committed))
    bad = [f"  missing from the lookup: {p}" for p in diff["missing"]] + [f"  not in the committed record: {p}" for p in diff["added"]]
    bad += [f"  classification changed: {c['pmcid']} {c['fields']}" for c in diff["classification"]]
    if bad:
        print("design-live: PubMed's classification differs from the committed record (the results are unchanged; a person decides "
              "whether to re-derive them, see data/m1/drift_log.md)", file=sys.stderr)
        print("\n".join(bad), file=sys.stderr)
        return 1
    print(f"design-live: classification identical for all {len(_rows(committed))} papers; PubMed's publication types changed for "
          f"{len(diff['types_only'])} (accepted, see data/m1/drift_log.md):")
    for t in diff["types_only"]:
        print(f"  {t['pmcid']}: added {t['added']} removed {t['removed']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("offline")
    lv = sub.add_parser("live")
    lv.add_argument("current", type=Path, help="the fresh lookup (scripts/fetch_design.py --out ...)")
    lv.add_argument("committed", type=Path, help="data/m1/design.jsonl")
    args = ap.parse_args()
    return offline() if args.cmd == "offline" else live(args.current, args.committed)


if __name__ == "__main__":
    raise SystemExit(main())
