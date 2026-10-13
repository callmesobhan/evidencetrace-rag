"""Check an annotation file against the papers it annotates (see docs/annotation-guidelines.md).

    python scripts/validate_annotations.py --inputs DIR --annotations annotations.jsonl [--out-of-scope out.jsonl]

DIR holds one canonical text file per paper, ``<doc_id>.txt``. Exit status 1 if anything is wrong. This checks
form and quote anchoring only: it cannot check that every estimate was found.
Standard library only, so a second annotator needs nothing installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

METRICS = {"HR", "OR", "RR", "IRR", "MD", "SMD", "RD"}
OPS = {"<", "=", ">", "<=", ">=", None}
CATEGORIES = {"unnamed_difference", "rate_or_proportion", "regression_coefficient", "rrr",
              "win_ratio_or_other_ratio", "balance_diagnostic", "planned_value", "within_arm_change", "other"}


def _num(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check(inputs: Path, annotations: Path, out_of_scope: Path | None) -> list[str]:
    texts = {p.stem: p.read_text(encoding="utf-8") for p in inputs.glob("*.txt") if not p.name.endswith(".view.txt")}
    errors: list[str] = []
    seen: set[tuple] = set()

    def load(path: Path) -> list[tuple[int, dict]]:
        out = []
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                out.append((i, json.loads(line)))
            except json.JSONDecodeError as exc:
                errors.append(f"{path.name}:{i}: not valid JSON ({exc})")
        return out

    for i, r in load(annotations):
        where = f"{annotations.name}:{i}"
        doc = r.get("doc_id")
        if doc not in texts:
            errors.append(f"{where}: unknown doc_id {doc!r}")
            continue
        q = r.get("quote")
        if not isinstance(q, str) or not q or q not in texts[doc]:
            errors.append(f"{where}: quote not found verbatim in {doc}: {str(q)[:60]!r}")
        if r.get("metric") not in METRICS:
            errors.append(f"{where}: metric must be one of {sorted(METRICS)}")
        if not _num(r.get("value")):
            errors.append(f"{where}: value must be a number")
        ci = r.get("ci")
        if ci is not None and not (isinstance(ci, list) and len(ci) == 2 and all(map(_num, ci)) and ci[0] <= ci[1]):
            errors.append(f"{where}: ci must be null or [low, high] with low <= high")
        if r.get("p_value") is not None and not _num(r["p_value"]):
            errors.append(f"{where}: p_value must be a number or null")
        if r.get("p_operator") not in OPS:
            errors.append(f"{where}: p_operator must be one of < = > <= >= or null")
        if r.get("attribution") not in {"own", "cited"}:
            errors.append(f"{where}: attribution must be 'own' or 'cited'")
        key = (doc, r.get("metric"), r.get("value"), tuple(ci) if isinstance(ci, list) else None)
        if key in seen:
            errors.append(f"{where}: duplicate estimate {key[1:]} in {doc} (record each distinct estimate once)")
        seen.add(key)

    if out_of_scope:
        for i, r in load(out_of_scope):
            where = f"{out_of_scope.name}:{i}"
            if r.get("doc_id") not in texts:
                errors.append(f"{where}: unknown doc_id {r.get('doc_id')!r}")
            elif r.get("quote") not in texts[r["doc_id"]]:
                errors.append(f"{where}: quote not found verbatim")
            if r.get("category") not in CATEGORIES:
                errors.append(f"{where}: category must be one of {sorted(CATEGORIES)}")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", type=Path, required=True)
    ap.add_argument("--annotations", type=Path, required=True)
    ap.add_argument("--out-of-scope", type=Path)
    args = ap.parse_args()
    errors = check(args.inputs, args.annotations, args.out_of_scope)
    for e in errors[:100]:
        print(e, file=sys.stderr)
    n = sum(1 for ln in args.annotations.read_text().splitlines() if ln.strip())
    print(f"{n} annotation(s); {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
