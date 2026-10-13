"""Command line: ``evidencetrace ingest | ask | inspect | eval``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evidencetrace.config import Config
from evidencetrace.pipeline import EvidencePipeline
from evidencetrace.render import render_answer


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--workspace", default=".evidencetrace", help="directory for docs + findings")
    p.add_argument("--config", default=None, help="TOML config (see configs/default.toml)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidencetrace", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="parse papers and extract findings")
    p_ing.add_argument("paths", nargs="+")
    _common(p_ing)

    p_ask = sub.add_parser("ask", help="ask a question; answers or abstains")
    p_ask.add_argument("query")
    p_ask.add_argument("--json", action="store_true", help="emit the Answer as JSON")
    _common(p_ask)

    p_ins = sub.add_parser("inspect", help="show a finding's source span in context")
    p_ins.add_argument("finding_id")
    p_ins.add_argument("--context", type=int, default=160, help="chars of context each side")
    _common(p_ins)

    p_ev = sub.add_parser("eval", help="run the evaluation harness")
    p_ev.add_argument("--corpus", required=True, help="directory of papers")
    p_ev.add_argument("--gold", required=True, help="directory with gold_findings.jsonl + gold_queries.jsonl")
    p_ev.add_argument("--out", default="reports")
    p_ev.add_argument("--config", default=None)

    args = parser.parse_args(argv)
    cfg = Config.load(args.config)

    if args.cmd == "ingest":
        rep = EvidencePipeline(args.workspace, cfg).ingest_paths(args.paths)
        print(f"ingested {rep.documents} document(s): {rep.findings} findings "
              f"({rep.own} own, {rep.cited} cited)")
        return 0

    if args.cmd == "ask":
        ans = EvidencePipeline(args.workspace, cfg).ask(args.query)
        print(ans.model_dump_json(indent=2) if args.json else render_answer(ans))
        return 0

    if args.cmd == "inspect":
        pipe = EvidencePipeline(args.workspace, cfg)
        docs = pipe.ws.load_documents()
        match = next((f for f in pipe.ws.load_findings() if f.finding_id == args.finding_id), None)
        if match is None:
            print(f"no finding {args.finding_id!r}", file=sys.stderr)
            return 1
        text = docs[match.doc_id].text
        s, e = match.span.start, match.span.end
        lo, hi = max(0, s - args.context), min(len(text), e + args.context)
        print(f"{match.span.citation}  [{match.span.section}]  {match.brief()}\n")
        print(f"...{text[lo:s]}>>>{text[s:e]}<<<{text[e:hi]}...")
        return 0

    if args.cmd == "eval":
        from evidencetrace.evaluation.runner import run_evaluation, write_reports

        report = run_evaluation(Path(args.corpus), Path(args.gold), cfg)
        json_path, md_path = write_reports(report, Path(args.out))
        print(Path(md_path).read_text(encoding="utf-8"))
        print(f"\nwrote {json_path} and {md_path}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
