"""Plain-text adjudication forms, for a judge who cannot open the review page.

``render_form`` writes the items of a review page as a .txt file with an ANSWER / REASON / NOTE line under each item;
``parse_form`` reads the filled-in file back into the records the page's "Download decisions" button exports, and refuses
anything it cannot read unambiguously (unanswered item, unknown answer, missing or duplicated item, form meant for the other judge).
"""

from __future__ import annotations

import json
import re
import textwrap

FORM_VERSION = "rules-round-v1.2"
WIDTH = 96

# the same menu as the page (scripts/make_adjudication_page.py)
REASONS = {
    "balance": "baseline balance / SMD diagnostic",
    "within_arm": "within-arm change",
    "planned": "planned / threshold value",
    "unnamed": "unnamed difference / effect size",
    "rate": "rate, proportion or mean",
    "coef": "regression coefficient / correlation",
    "duplicate": "duplicate of another item",
    "other": "other",
}
ANSWERS = {"yes": "yes", "y": "yes", "no": "no", "n": "no", "unsure": "unk", "u": "unk", "unk": "unk"}

NOTICES = {
    "owner": "Fill this in on your own, before you look at anyone else's answers.",
    "second": (
        "You are the second, independent adjudicator. Please judge each item yourself: do not open the repository's "
        "data/m1/independent/adjudication/ folder (it holds the earlier verdicts) and do not discuss the items with the first "
        "adjudicator until you have sent your file back. Please answer without AI tools; if you used any, say so on the AI line "
        "at the end. Nothing in this file asks for your name."
    ),
}

SCOPE_SUMMARY = (
    "In general, an item is in scope if it is a between-group point estimate (HR, OR, RR, IRR, MD, SMD, RD; optionally with CI and p). "
    "It is not in scope if it is a planned or hypothetical value, a baseline-balance statistic, a within-arm change, a rate or "
    "proportion, a regression coefficient, or an unnamed difference. You are judging the estimate, not who found it."
)

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_HEADER = re.compile(r"^=+ ITEM (\d+) of (\d+) +\[id ([0-9a-f]{10})\] =+\s*$")
_LABEL = {name: re.compile(rf"^\s*{name}\b[^:\n]*:\s*(.*)$", re.IGNORECASE) for name in ("ANSWER", "REASON", "NOTE")}


class FormError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _wrap(text: str, indent: str = "", gutter: str = "", hang: str = "") -> str:
    """Wrap to WIDTH without splitting words or URLs at hyphens; ``hang`` indents continuation lines of a numbered step."""
    return textwrap.fill(" ".join(text.split()), WIDTH, initial_indent=indent + gutter, subsequent_indent=indent + gutter + hang,
                         break_on_hyphens=False, break_long_words=False)


def highlight(text: str, nums: list[float]) -> str:
    """Mark the numbers of the estimate inside its sentence, as the page does with <mark>."""
    return _NUM.sub(lambda m: f"[[{m.group(0)}]]" if any(abs(n - abs(float(m.group(0)))) < 1e-9 for n in nums) else m.group(0), text)


def _item_block(n: int, total: int, it: dict) -> str:
    ci = f" ({it['ci'][0]} to {it['ci'][1]})" if it.get("ci") else ""
    found = ("the SYSTEM extracted this; the annotator did not" if it["type"] == "system_only"
             else "the ANNOTATOR recorded this; the system did not")
    nums = [abs(it["value"])] + [abs(c) for c in (it.get("ci") or [])]
    ctx = f"{it.get('before') or ''} >>> {highlight(it['sentence'], nums)} <<< {it.get('after') or ''}".strip()
    return "\n".join([
        f"===== ITEM {n} of {total}   [id {it['id']}] =====",
        f"Paper: {it['pmcid']}  https://pmc.ncbi.nlm.nih.gov/articles/{it['pmcid']}/" + (f"   (section: {it['section']})" if it.get("section") else ""),
        f"Found by: {found}",
        f"Estimate: {it['metric']} {it['value']}{ci}",
        "Text (the estimate is between >>> and <<<; its numbers are in [[double brackets]]):",
        _wrap(ctx, "  ", "| "),
        "Question: is this estimate a genuine in-scope effect estimate under the rules above?",
        "ANSWER (yes / no / unsure): ",
        "REASON (only if no; choose from " + ", ".join(REASONS) + "): ",
        "NOTE (optional, one line): ",
    ])


def render_form(items: list[dict], intro: str, who: str) -> str:
    if who not in NOTICES:
        raise ValueError(who)
    est = [i for i in items if i["kind"] == "estimate"]
    out = [
        f"SCOPE-RULE RE-JUDGEMENT, {len(est)} ITEMS  (EvidenceTrace-RAG, annotation guidelines v1.2)",
        f"FORM-FOR: {who}",
        f"FORM-VERSION: {FORM_VERSION}",
        "",
        "HOW TO FILL THIS IN",
        _wrap("1. Open this file in a plain-text editor (Mac: TextEdit, then Format > Make Plain Text; Windows: Notepad).", "  ", hang="   "),
        _wrap(f"2. For each of the {len(est)} items, type your answer after the colon on the ANSWER line: yes, no or unsure.", "  ", hang="   "),
        _wrap("3. If your answer is no, you may add a REASON (one word from the list below) and a NOTE (one line). A short note is useful "
              "wherever you applied a rule.", "  ", hang="   "),
        _wrap("4. Do not change the ITEM lines or the ids in brackets. Keep each answer on one line.", "  ", hang="   "),
        _wrap("5. Save the file and send it back as it is. About 20 minutes.", "  ", hang="   "),
        "",
        _wrap(NOTICES[who]),
        "",
        "THE RULES",
        "\n\n".join(_wrap(par, "  ") for par in re.split(r"\n\s*\n", intro.strip()) if par.strip()),
        "",
        _wrap(SCOPE_SUMMARY, "  "),
        _wrap("The full guidelines: https://github.com/callmesobhan/evidencetrace-rag/blob/main/docs/annotation-guidelines.md (the v1.2 "
              "addendum is at the end).", "  "),
        "",
        "REASON CODES (for a \"no\")",
        *[f"  {k:<11} {v}" for k, v in REASONS.items()],
        "",
        *[line for n, it in enumerate(est, 1) for line in (_item_block(n, len(est), it), "")],
        "AT THE END",
        "AI ASSISTANCE (no / yes, describe): ",
        "",
    ]
    return "\n".join(out)


def parse_form(text: str, items: list[dict], who: str) -> tuple[list[dict], dict]:
    """Return (records in the page's export format, meta). Raises FormError listing every problem found."""
    est = {i["id"]: i for i in items if i["kind"] == "estimate"}
    lines = text.lstrip("﻿").splitlines()
    problems: list[str] = []
    form_for = next((m.group(1).lower() for ln in lines if (m := re.match(r"^\s*FORM-FOR:\s*(\w+)", ln))), None)
    if form_for != who:
        problems.append(f"this form is for {form_for or 'nobody (no FORM-FOR line)'}, not for {who}")
    blocks: dict[str, list[str]] = {}
    current = None
    ai_statement = None
    for ln in lines:
        if m := _HEADER.match(ln):
            current = m.group(3)
            if current in blocks:
                problems.append(f"item [{current}] appears twice")
            blocks.setdefault(current, [])
        elif current is not None:
            if ln.startswith("AT THE END"):
                current = None
            else:
                blocks[current].append(ln)
        elif m := re.match(r"^\s*AI ASSISTANCE\b[^:\n]*:\s*(.*)$", ln, re.IGNORECASE):
            ai_statement = m.group(1).strip()
    for missing in [i for i in est if i not in blocks]:
        problems.append(f"item [{missing}] is missing from the file")
    for unknown in [i for i in blocks if i not in est]:
        problems.append(f"item [{unknown}] is not one of the {len(est)} items")
    records, warnings = [], []
    for n, (iid, it) in enumerate(est.items(), 1):
        body = blocks.get(iid)
        if body is None:
            continue
        got: dict[str, str] = {}
        for ln in body:
            if ln.lstrip().startswith("|"):
                continue
            for name, rx in _LABEL.items():
                if name not in got and (m := rx.match(ln)):
                    got[name] = m.group(1).strip()
        word = re.match(r"^[\s\"'(]*([A-Za-z]+)", got.get("ANSWER", ""))
        decision = ANSWERS.get(word.group(1).lower()) if word else None
        if decision is None:
            problems.append(f"item {n} [{iid}]: ANSWER is " + (f"{got['ANSWER']!r}, which is not yes, no or unsure" if got.get("ANSWER") else "empty"))
            continue
        reason = re.sub(r"[\s-]+", "_", got.get("REASON", "").strip().lower()) or None
        if reason is not None and reason not in REASONS:
            problems.append(f"item {n} [{iid}]: REASON {got['REASON']!r} is not one of {', '.join(REASONS)}")
            continue
        if reason is not None and decision != "no":
            warnings.append(f"item {n} [{iid}]: a REASON was given with answer {decision}; the reason is dropped")
            reason = None
        records.append({"id": iid, "kind": "estimate", "pmcid": it["pmcid"], "decision": decision, "reason": reason,
                        "note": got.get("NOTE") or None})
    if ai_statement is None:
        warnings.append("the AI ASSISTANCE line is missing")
    elif not ai_statement:
        warnings.append("the AI ASSISTANCE line is empty")
    if problems:
        raise FormError(problems)
    return records, {"form_for": form_for, "ai_assistance": ai_statement, "warnings": warnings}


def records_jsonl(records: list[dict]) -> str:
    """The page's export format (compact JSON, one record per line)."""
    return "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records)
