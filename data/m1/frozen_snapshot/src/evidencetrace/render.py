"""Plain-text rendering of an Answer, with the source quote under every number."""

from __future__ import annotations

import textwrap

from evidencetrace.schemas import Answer, AnswerStatus, Finding


def _finding_block(i: int, f: Finding) -> list[str]:
    who = " vs ".join(x for x in (f.intervention, f.comparator) if x) or "?"
    lines = [
        f"  [{i}] {who} -> {f.outcome or '?'}",
        f"      {f.brief()}",
        f"      source: {f.span.citation}  (section: {f.span.section})",
    ]
    quote = textwrap.fill(f.span.text, 88, initial_indent='      "', subsequent_indent="       ")
    lines.append(quote + '"')
    return lines


def render_answer(ans: Answer) -> str:
    out = [f"Q: {ans.query}", f"STATUS: {ans.status.value.upper()}  (confidence {ans.confidence:.2f})"]
    out.append(ans.summary)
    if ans.findings:
        out += ["", "Findings"]
        index = {}
        for i, f in enumerate(ans.findings, 1):
            index[f.finding_id] = i
            out += _finding_block(i, f)
    if ans.conflicts:
        out += ["", "Conflicts"]
        for c in ans.conflicts:
            a, b = index[c.finding_a], index[c.finding_b]
            out.append(f"  ! {c.kind.value.upper()} ({c.severity}) between [{a}] and [{b}]")
            out.append(textwrap.fill(c.explanation, 88, initial_indent="    ", subsequent_indent="    "))
    for caveat in ans.caveats:
        out += ["", textwrap.fill(f"Caveat: {caveat}", 88, subsequent_indent="  ")]
    if ans.status is AnswerStatus.ABSTAINED and ans.nearest_evidence:
        out += ["", "Closest evidence found (NOT an answer to the question asked)"]
        for i, f in enumerate(ans.nearest_evidence, 1):
            out += _finding_block(i, f)
    return "\n".join(out)
