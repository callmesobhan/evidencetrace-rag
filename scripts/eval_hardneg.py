"""Score a system on the hard-negative queries: every one should be refused.

    python -I scripts/eval_hardneg.py --raw data/raw/pmc --m1 data/m1 --out OUT [--config configs/posthoc.toml]
    PYTHONPATH=data/m1/frozen_snapshot/src python scripts/eval_hardneg.py --frozen ...   # the frozen source

Self-contained on purpose (no helper imports beyond what the frozen snapshot also has), so the same script measures
the frozen source, the current code, and any later fix. Intervals are exact (Clopper-Pearson); with a handful of
queries the bootstrap would be meaningless.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from math import comb
from pathlib import Path

import evidencetrace
from evidencetrace.config import Config
from evidencetrace.evaluation.m1 import load_split
from evidencetrace.pipeline import EvidencePipeline
from evidencetrace.schemas import AnswerStatus


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided binomial interval for k events in n trials."""
    if n == 0:
        return (0.0, 1.0)

    def cdf(x: int, p: float) -> float:
        return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(x + 1))

    def bisect(f, lo: float, hi: float) -> float:
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) else (lo, mid)
        return (lo + hi) / 2

    upper = 1.0 if k == n else bisect(lambda p: cdf(k, p) > alpha / 2, 0.0, 1.0)
    lower = 0.0 if k == 0 else bisect(lambda p: 1 - cdf(k - 1, p) < alpha / 2, 0.0, 1.0)
    return (round(lower, 4), round(upper, 4))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--m1", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--frozen", action="store_true", help="require the frozen source (PYTHONPATH, not python -I)")
    args = ap.parse_args()
    where = Path(evidencetrace.__file__).resolve().parent
    print(f"evidencetrace imported from: {where}", file=sys.stderr)
    if args.frozen and (args.m1 / "frozen_snapshot").resolve() not in where.parents:
        sys.exit(f"error: --frozen needs the frozen source but evidencetrace came from {where}")
    cfg = Config.load(args.config)
    args.out.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    for split in ("dev", "test"):
        qpath = args.m1 / "queries" / f"{split}_hardneg_queries.jsonl"
        queries = [json.loads(ln) for ln in qpath.read_text().splitlines() if ln.strip()]
        docs = load_split(args.raw, split)
        with tempfile.TemporaryDirectory() as tmp:
            pipe = EvidencePipeline(Path(tmp) / "ws", cfg)
            pipe.ingest_documents(docs.values())
            rows = []
            for q in queries:
                ans = pipe.ask(q["query"])
                answered = ans.status is not AnswerStatus.ABSTAINED
                rows.append({"qid": q["qid"], "query": q["query"], "answered": answered, "status": ans.status.value,
                             "returned": [f"{f.doc_id}: {f.brief()}" for f in ans.findings[:2]]})
        k, n = sum(r["answered"] for r in rows), len(rows)
        report[split] = {"n": n, "false_answers": k, "rate": round(k / n, 4) if n else None,
                         "exact_95_ci": clopper_pearson(k, n), "queries": rows}
        print(f"{split}: {k}/{n} hard negatives answered (exact 95% CI {report[split]['exact_95_ci']})")
    (args.out / "hardneg.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
