"""Check every hash recorded in data/m1/FROZEN.json against the files in this checkout. Standard library only.

    python scripts/verify_freeze.py            # exit 1 if anything does not match

Hash algorithms (so they can be re-implemented):
  * tree hash  - sha256 over, for every file under a directory (``__pycache__`` excluded) in ascending order of its
                 POSIX relative path: the relative path as UTF-8, then the file's bytes.
  * file hash  - sha256 of the file's bytes.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
M1 = ROOT / "data" / "m1"


def tree_sha256(root: Path) -> str:
    h = hashlib.sha256()
    files = sorted((f.relative_to(root).as_posix(), f) for f in root.rglob("*") if f.is_file() and "__pycache__" not in f.parts)
    for rel, f in files:
        h.update(rel.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _holdout2(rec: dict) -> list[tuple[str, str, str]]:
    h = rec.get("holdout2")
    if not h:
        return []
    return [
        ("source that made the holdout-2 predictions (data/m1/frozen_snapshot_holdout2)", h["src_sha256"], tree_sha256(M1 / "frozen_snapshot_holdout2")),
        ("holdout-2 predictions (data/m1/independent/holdout2/predictions.jsonl)", h["predictions_sha256"], file_sha256(M1 / "independent" / "holdout2" / "predictions.jsonl")),
    ]


def checks(rec: dict) -> list[tuple[str, str, str]]:
    """(label, recorded, actual) for each verifiable claim."""
    fresh = rec["fresh_holdout"]
    return [
        ("frozen source + config (data/m1/frozen_snapshot)", rec["code_and_config_sha256"], tree_sha256(M1 / "frozen_snapshot")),
        ("dev gold (data/m1/gold/dev_gold_findings.jsonl)", rec["dev_gold_sha256"], file_sha256(M1 / "gold" / "dev_gold_findings.jsonl")),
        ("pinned corpus manifest (data/m1/corpus_manifest.jsonl)", rec["pinned_manifest_sha256"], file_sha256(M1 / "corpus_manifest.jsonl")),
        ("fresh corpus manifest (data/m1/fresh_manifest.jsonl)", fresh["manifest_sha256"], file_sha256(M1 / "fresh_manifest.jsonl")),
        ("source that made the held-out fresh predictions (data/m1/frozen_snapshot_fresh)", fresh["src_sha256"], tree_sha256(M1 / "frozen_snapshot_fresh")),
        ("held-out fresh predictions (data/m1/independent/predictions_prefix.jsonl)", fresh["predictions_sha256"], file_sha256(M1 / "independent" / "predictions_prefix.jsonl")),
    ] + _holdout2(rec)


def pinned_checks(rec: dict) -> list[tuple[str, str, str]]:
    out = []
    for rel, want in rec.get("pinned_files", {}).get("files", {}).items():
        path = M1 / rel
        out.append((f"data/m1/{rel}", want, file_sha256(path) if path.is_file() else "(missing)"))
    return out


def main() -> int:
    rec = json.loads((M1 / "FROZEN.json").read_text(encoding="utf-8"))
    bad = 0
    for label, want, got in checks(rec):
        ok = want == got
        bad += not ok
        print(f"{'ok      ' if ok else 'MISMATCH'}  {label}" + ("" if ok else f"\n          recorded {want}\n          actual   {got}"))
    pinned = pinned_checks(rec)
    wrong = [(label, want, got) for label, want, got in pinned if want != got]
    for label, want, got in wrong:
        print(f"MISMATCH  {label}\n          recorded {want}\n          actual   {got}")
    bad += len(wrong)
    print(f"ok        {len(pinned) - len(wrong)}/{len(pinned)} pinned evaluation files (gold, queries, annotation, independent pack)")
    print("all recorded hashes verified" if not bad else f"{bad} hash(es) do not match")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
