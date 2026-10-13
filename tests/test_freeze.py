"""Every hash in data/m1/FROZEN.json must be recomputable from the committed files."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verify_freeze", ROOT / "scripts" / "verify_freeze.py")
vf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vf)


def test_recorded_hashes_match_the_committed_files():
    rec = json.loads((vf.M1 / "FROZEN.json").read_text(encoding="utf-8"))
    results = vf.checks(rec)
    assert len(results) >= 6
    bad = [label for label, want, got in [*results, *vf.pinned_checks(rec)] if want != got]
    assert not bad, f"FROZEN.json disagrees with: {bad} (run python scripts/verify_freeze.py)"


def test_tree_hash_ignores_bytecode_and_depends_on_names_and_bytes(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.py").write_text("1")
    h1 = vf.tree_sha256(tmp_path)
    (tmp_path / "a" / "__pycache__").mkdir()
    (tmp_path / "a" / "__pycache__" / "x.pyc").write_bytes(b"junk")
    assert vf.tree_sha256(tmp_path) == h1
    (tmp_path / "a" / "x.py").write_text("2")
    assert vf.tree_sha256(tmp_path) != h1
    (tmp_path / "a" / "x.py").write_text("1")
    (tmp_path / "a" / "x.py").rename(tmp_path / "a" / "y.py")
    assert vf.tree_sha256(tmp_path) != h1
