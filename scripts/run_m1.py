"""Score the frozen system on the M1 splits and write results.

    python -I scripts/run_m1.py --raw data/raw/pmc --m1 data/m1 --out OUTDIR [--config configs/posthoc.toml]
    PYTHONPATH=data/m1/frozen_snapshot/src python scripts/run_m1.py --frozen --raw data/raw/pmc --m1 data/m1 --out OUTDIR

Lives in scripts/ (not src/) on purpose: the code freeze recorded in data/m1/FROZEN.json covers
src/ and configs/, and reporting must not be able to alter what is being measured.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import evidencetrace
from evidencetrace.config import Config
from evidencetrace.evaluation.m1 import fmt_ci, run_split, split_markdown
from evidencetrace.evaluation.m1_queries import run_queries


def queries_markdown(r: dict) -> str:
    a, u = r["answerable"], r["unanswerable"]
    q = r["queries"]
    lines = [
        f"### `{r['split']}` split - abstention on {sum(q.values())} queries "
        f"({q['annotated']} annotated-wording, {q['paraphrase']} paraphrase, {q['cross']} cross, {q['absent']} absent)",
        "",
        "| metric | value (95% bootstrap CI over queries) |",
        "|---|---|",
        f"| **false-answer rate** (answered an unanswerable query), n={u['n']} | {fmt_ci(u['false_answer_rate'])} |",
        f"| - cross (real drug x another paper's outcome) | {fmt_ci(u.get('cross_false_answer'))} |",
        f"| - absent (real drug x outcome nowhere in corpus) | {fmt_ci(u.get('absent_false_answer'))} |",
        f"| **over-abstention rate** (refused an answerable query), n={a['n']} | {fmt_ci(a['over_abstention_rate'])} |",
        f"| - annotated wording | {fmt_ci(a.get('annotated_over_abstention'))} |",
        f"| - hand-written paraphrase | {fmt_ci(a.get('paraphrase_over_abstention'))} |",
        f"| answerable queries whose target finding was returned (hit rate) | {fmt_ci(a['hit_rate'])} |",
        f"| AURC (lower is better) | {r['aurc']:.3f} |",
        f"| conflicts reported / answers carrying an 'unassessed pairs' caveat | {r['conflicts_reported']} / {r['answers_with_unassessed_pairs']} |",
    ]
    return "\n".join(lines)


def _rounded(obj, digits: int = 12):
    """Round floats for the JSON files. Python 3.12 made float ``sum()`` compensated, so the last bits of a
    mean can differ between interpreters; 12 digits is far below any reported precision and identical everywhere."""
    if isinstance(obj, float):
        return round(obj, digits)
    if isinstance(obj, dict):
        return {k: _rounded(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_rounded(v, digits) for v in obj]
    return obj


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--m1", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--config", type=Path, default=None, help="TOML overriding configs/default.toml")
    ap.add_argument("--frozen", action="store_true",
                    help="refuse to run unless evidencetrace is imported from data/m1/frozen_snapshot (use with PYTHONPATH, NOT python -I)")
    ap.add_argument("--label-corrections", type=Path, default=None, help="JSON {split: [qid,...]} of audited label errors to exclude")
    args = ap.parse_args()
    where = Path(evidencetrace.__file__).resolve().parent
    print(f"evidencetrace imported from: {where}", file=sys.stderr)
    if args.frozen and (args.m1 / "frozen_snapshot").resolve() not in where.parents:
        sys.exit(f"error: --frozen needs the frozen source, but evidencetrace came from {where}.\n"
                 f"Run: PYTHONPATH={args.m1}/frozen_snapshot/src python scripts/run_m1.py --frozen ...  (no -I: -I ignores PYTHONPATH)")
    args.out.mkdir(parents=True, exist_ok=True)
    cfg = Config.load(args.config)
    excl = json.loads(args.label_corrections.read_text()) if args.label_corrections else {}
    for split in ("dev", "test"):
        ext = run_split(args.raw, split, args.m1 / "annotation", args.m1 / "gold", cfg, reps=args.reps)
        ext.pop("_mapping", None)
        # `exclude` only exists in post-freeze code; omit it when unused so the frozen snapshot still runs
        extra = {"exclude": {q["qid"] for q in excl[split]}} if excl.get(split) else {}
        qry = run_queries(args.raw, split, args.m1 / "gold", args.m1 / "queries" / f"{split}_queries.jsonl",
                          cfg, reps=args.reps, **extra)
        (args.out / f"{split}.json").write_text(json.dumps(_rounded({"extraction": ext, "abstention": qry}), indent=1), encoding="utf-8")
        md = split_markdown(ext) + "\n\n" + queries_markdown(qry)
        (args.out / f"{split}.md").write_text(md + "\n", encoding="utf-8")
        print(md, "\n")


if __name__ == "__main__":
    main()
