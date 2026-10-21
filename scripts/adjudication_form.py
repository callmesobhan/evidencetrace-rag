"""Plain-text forms for the scope-rule re-judgement, for a judge who cannot open the review page.

    python -I scripts/adjudication_form.py make  --who owner  --out form_owner.txt
    python -I scripts/adjudication_form.py parse --who owner  --form form_owner_filled.txt --out decisions_owner.jsonl

The 14 items are read from the published page (docs/adjudication-rules.html), so the form and the page cannot differ. ``parse`` checks
the filled-in file strictly and writes the records the page's "Download decisions" button would have exported.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from evidencetrace.evaluation.adjudication_form import FormError, parse_form, records_jsonl, render_form

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "adjudication-rules.html"
INTRO = ROOT / "data" / "m1" / "independent" / "adjudication" / "rules_round" / "intro.txt"


def page_items(page: Path = PAGE) -> list[dict]:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:  # an editor that saved in the system code page: only the text lines are affected
        return raw.decode("cp1252", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("--who", choices=["owner", "second"], required=True)
    mk.add_argument("--out", type=Path, required=True)
    ps = sub.add_parser("parse")
    ps.add_argument("--who", choices=["owner", "second"], required=True)
    ps.add_argument("--form", type=Path, required=True)
    ps.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    items = page_items()
    if args.cmd == "make":
        intro = INTRO.read_text(encoding="utf-8")
        assert "This page re-judges" in intro
        args.out.write_text(render_form(items, intro.replace("This page re-judges", "This form re-judges"), args.who), encoding="utf-8")
        print(f"{sum(i['kind'] == 'estimate' for i in items)} items -> {args.out}")
        return 0
    try:
        records, meta = parse_form(read_text(args.form), items, args.who)
    except FormError as exc:
        print(f"{args.form} cannot be used:", file=sys.stderr)
        for p in exc.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    args.out.write_text(records_jsonl(records), encoding="utf-8")
    tally = {d: sum(r["decision"] == d for r in records) for d in ("yes", "no", "unk")}
    print(f"{len(records)} verdicts -> {args.out}   (yes {tally['yes']}, no {tally['no']}, unsure {tally['unk']})")
    print(f"AI assistance, as stated: {meta['ai_assistance']!r}")
    for w in meta["warnings"]:
        print(f"  warning: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
