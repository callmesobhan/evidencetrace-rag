"""Refresh the derived parts of data/m1/FROZEN.json after code or data changes. Standard library only.

    python scripts/refresh_freeze_record.py

Recomputes (1) which source files differ between the preserved snapshots and the current tree and (2) the hash of every
pinned evaluation input. It never touches the hashes of the two frozen snapshots themselves: those must not change.
"""

from __future__ import annotations

import filecmp
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_freeze as vf  # noqa: E402

M1, ROOT = vf.M1, vf.ROOT
PINNED_GLOBS = ("gold/*.jsonl", "gold/*.json", "queries/*", "annotation/*.json", "annotation/*.jsonl", "annotation/v1/*.jsonl",
                "independent/pack/**/*", "design.jsonl")


def _files(root: Path) -> set[str]:
    return {f.relative_to(root).as_posix() for f in root.rglob("*") if f.is_file() and "__pycache__" not in f.parts}


def _changed(a: Path, b: Path) -> dict[str, list[str]]:
    fa, fb = _files(a), _files(b)
    return {"changed": sorted(x for x in fa & fb if not filecmp.cmp(a / x, b / x, shallow=False)),
            "added": sorted(fb - fa), "removed": sorted(fa - fb)}


def main() -> int:
    rec = json.loads((M1 / "FROZEN.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:  # the current tree laid out like the snapshots
        cur = Path(tmp)
        shutil.copytree(ROOT / "src", cur / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        (cur / "configs").mkdir()
        shutil.copy(ROOT / "configs" / "default.toml", cur / "configs" / "default.toml")
        rec["post_hoc"]["files_changed_between_test_freeze_and_fresh_holdout_freeze"] = _changed(M1 / "frozen_snapshot", M1 / "frozen_snapshot_fresh")
        rec["post_review"]["files_changed_since_fresh_holdout_freeze"] = _changed(M1 / "frozen_snapshot_fresh", cur)
    pinned = {f.relative_to(M1).as_posix(): vf.file_sha256(f) for pat in PINNED_GLOBS for f in sorted(M1.glob(pat)) if f.is_file()}
    rec["pinned_files"] = {"algorithm": "file hash (sha256 of bytes); paths relative to data/m1/", "files": pinned}
    (M1 / "FROZEN.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"FROZEN.json refreshed: {len(pinned)} pinned files; "
          f"{len(rec['post_review']['files_changed_since_fresh_holdout_freeze']['changed'])} source files differ from the fresh-holdout snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
