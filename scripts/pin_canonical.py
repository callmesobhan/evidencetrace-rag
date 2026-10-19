"""Write data/m1/canonical_pins.jsonl: the SHA-256 of the canonical text each pinned paper yields.

    python scripts/pin_canonical.py          # needs the pinned papers: make fetch-pinned (or the committed-bytes copies)

Refuses to run unless every local file matches its raw SHA-256 in the manifests, so the canonical pins describe exactly the bytes that
were pinned. fetch_pmc.py accepts a fetched record when its canonical text matches (PMC bookkeeping may change; content may not).
"""

from __future__ import annotations

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from evidencetrace.ingest.pmc import canonical_sha256, split_articles

ROOT = Path(__file__).resolve().parent.parent
M1 = ROOT / "data" / "m1"


def main() -> int:
    rows, seen = [], set()
    for manifest, raw in ((M1 / "corpus_manifest.jsonl", ROOT / "data/raw/pmc"), (M1 / "fresh_manifest.jsonl", ROOT / "data/raw/fresh")):
        for ln in manifest.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            pin = json.loads(ln)
            path = raw / f"{pin['pmcid']}.xml"
            if not path.exists():
                sys.exit(f"missing {path}: run make fetch-pinned first")
            art = dict(split_articles(path.read_text(encoding="utf-8")))[pin["pmcid"]]
            raw_sha = hashlib.sha256(ET.tostring(art, encoding="unicode").encode("utf-8")).hexdigest()
            if raw_sha != pin["sha256"]:
                sys.exit(f"{path} does not match its pinned raw SHA-256; refusing to pin its canonical text")
            if pin["pmcid"] in seen:
                sys.exit(f"{pin['pmcid']} is in both manifests")
            seen.add(pin["pmcid"])
            rows.append({"pmcid": pin["pmcid"], "split": pin["split"], "canonical_sha256": canonical_sha256(art)})
    rows.sort(key=lambda r: r["pmcid"])
    (M1 / "canonical_pins.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print(f"canonical pins for {len(rows)} papers -> data/m1/canonical_pins.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
