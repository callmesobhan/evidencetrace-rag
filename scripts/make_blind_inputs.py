"""Build blind annotation packs: opaque paper ids, canonical text, per-annotator assignments.

    python -I scripts/make_blind_inputs.py --fresh data/raw/fresh --raw data/raw/pmc --agree 6 \\
        --annotators 7 --out /path/to/blind --map /path/outside/pack/blind_map.json

Papers from ``--fresh`` (never seen by the system's developer) plus ``--agree`` papers from the existing
TEST split (to measure agreement with the developer's gold) are shuffled together under ids P01..Pnn, so an
annotator cannot tell which is which. The id->PMCID map is written OUTSIDE the pack.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from evidencetrace.ingest.parsers import parse_file


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", type=Path, required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--agree", type=int, default=6)
    ap.add_argument("--annotators", type=int, default=7)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--map", type=Path, required=True)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    fresh = sorted(p.stem for p in args.fresh.glob("PMC*.xml"))
    test = sorted(json.loads(ln)["pmcid"] for ln in (args.raw / "manifest.jsonl").read_text().splitlines()
                  if ln.strip() and json.loads(ln)["split"] == "test")
    agree = rng.sample(test, args.agree)
    items = [(p, args.fresh, "fresh") for p in fresh] + [(p, args.raw, "agreement") for p in agree]
    rng.shuffle(items)

    args.out.mkdir(parents=True, exist_ok=True)
    mapping, sizes = {}, {}
    for i, (pmcid, root, kind) in enumerate(items, 1):
        pid = f"P{i:02d}"
        doc = parse_file(root / f"{pmcid}.xml")
        (args.out / f"{pid}.txt").write_text(doc.text, encoding="utf-8")
        # reading aid: same paragraphs, with section names on their own lines (quotes must come from the .txt)
        view = []
        blocks = doc.text.split("\n\n")
        offset = 0
        for b in blocks:
            name = doc.section_at(offset)
            if not view or view[-1][0] != name:
                view.append((name, []))
            view[-1][1].append(b)
            offset += len(b) + 2
        (args.out / f"{pid}.view.txt").write_text(
            "\n\n".join(f"=== {n.upper()} ===\n\n" + "\n\n".join(bs) for n, bs in view), encoding="utf-8")
        mapping[pid] = {"pmcid": pmcid, "kind": kind}
        sizes[pid] = len(doc.text)

    ordered = sorted(sizes, key=lambda k: -sizes[k])
    buckets: list[list[str]] = [[] for _ in range(args.annotators)]
    loads = [0] * args.annotators
    for pid in ordered:  # greedy balance by length
        k = loads.index(min(loads))
        buckets[k].append(pid)
        loads[k] += sizes[pid]
    for k, b in enumerate(buckets, 1):
        (args.out / f"assignment_{k}.txt").write_text("\n".join(sorted(b)) + "\n", encoding="utf-8")
    args.map.write_text(json.dumps(mapping, indent=1), encoding="utf-8")
    print(f"{len(items)} papers ({len(fresh)} fresh + {len(agree)} agreement) -> {args.annotators} annotators; "
          f"chars per annotator: {loads}")


if __name__ == "__main__":
    main()
