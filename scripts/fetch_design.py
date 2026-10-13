"""Record the study design of every corpus paper in data/m1/design.jsonl (needs the papers and network once).

    python scripts/fetch_design.py            # reads data/raw/{pmc,fresh}, asks PubMed for publication types

The PMID of each paper comes from its own JATS metadata; PubMed's publication types and the title are combined by
``classify_design``. Re-running is idempotent as long as PubMed's indexing has not changed; the file is committed so the
numbers that depend on it do not.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidencetrace.ingest.design import classify_design, pmid_of
from evidencetrace.ingest.pmc import pubmed_publication_types

ROOT = Path(__file__).resolve().parent.parent
M1 = ROOT / "data" / "m1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=M1 / "design.jsonl")
    args = ap.parse_args()
    rows = []
    for manifest, raw in ((M1 / "corpus_manifest.jsonl", ROOT / "data/raw/pmc"), (M1 / "fresh_manifest.jsonl", ROOT / "data/raw/fresh")):
        for ln in manifest.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                xml = raw / f"{r['pmcid']}.xml"
                if not xml.exists():
                    sys.exit(f"missing {xml}: run `make fetch-pinned` first")
                rows.append({"pmcid": r["pmcid"], "split": r["split"], "title": r["title"], "pmid": pmid_of(xml.read_text(encoding="utf-8"))})
    missing = [r["pmcid"] for r in rows if not r["pmid"]]
    if missing:
        sys.exit(f"no PMID in the JATS of: {missing}")
    types = pubmed_publication_types([r["pmid"] for r in rows])
    out = []
    for r in sorted(rows, key=lambda r: r["pmcid"]):
        pt = types.get(r["pmid"], [])
        design, basis, disagree = classify_design(pt, r["title"])
        out.append({"pmcid": r["pmcid"], "pmid": r["pmid"], "split": r["split"], "pubmed_types": sorted(pt),
                    "design": design, "basis": basis, "disagree": disagree})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out), encoding="utf-8")
    from collections import Counter

    print(f"{len(out)} papers; no PubMed record for {sum(1 for o in out if not o['pubmed_types'])}")
    for split in ("dev", "test", "fresh"):
        print(f"  {split:5s}", dict(Counter(o["design"] for o in out if o["split"] == split)))
    print("  disagreements (PubMed vs title):", sum(o["disagree"] for o in out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
