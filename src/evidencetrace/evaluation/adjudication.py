"""Turn a human's verdicts on system-vs-annotator disagreements into corrected accuracy figures.

Each disagreement is either ``system_only`` (the system extracted an estimate the annotator did not record) or
``annotator_only`` (the annotator recorded one the system missed). A human answers one question per item: "is this a
genuine in-scope effect estimate?". Then:

* system_only  + in scope      -> the system was right: a true positive the annotation lacked (gold grows)
* system_only  + not in scope  -> a genuine false positive
* annotator_only + in scope    -> a genuine miss
* annotator_only + not in scope-> the annotator over-included (gold shrinks)

"Unsure" is never silently decided: figures are reported under three policies (exclude the item, resolve it in the system's
favour, resolve it against the system), which bound the answer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evidencetrace.evaluation.m1 import prf_ci

POLICIES = ("exclude", "favour_system", "against_system")


def item_id(r: dict) -> str:
    key = json.dumps([r["type"], r["pmcid"], r["metric"], r["value"], r.get("ci")], sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def load_decisions(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            if r["decision"] not in {"yes", "no", "unk"}:
                raise ValueError(f"unknown decision {r['decision']!r} for item {r['id']}")
            out[r["id"]] = r
    return out


def adjudicate(per_paper: list[dict], disagreements: list[dict], decisions: dict[str, dict], policy: str) -> list[dict[str, float]]:
    """Per-paper {tp, fp, fn} clusters after applying the verdicts under one policy for 'unsure'."""
    if policy not in POLICIES:
        raise ValueError(policy)
    gold = {p["pmcid"]: p["gold"] for p in per_paper}
    pred = {p["pmcid"]: p["pred"] for p in per_paper}
    tp = {p["pmcid"]: p["tp"] for p in per_paper}
    for r in disagreements:
        d = decisions.get(item_id(r))
        if d is None:
            continue  # undecided items keep their original status
        verdict = d["decision"]
        if verdict == "unk":
            if policy == "exclude":
                if r["type"] == "system_only":
                    pred[r["pmcid"]] -= 1
                else:
                    gold[r["pmcid"]] -= 1
                continue
            verdict = "yes" if (policy == "favour_system") == (r["type"] == "system_only") else "no"
        if r["type"] == "system_only" and verdict == "yes":
            tp[r["pmcid"]] += 1
            gold[r["pmcid"]] += 1
        elif r["type"] == "annotator_only" and verdict == "no":
            gold[r["pmcid"]] -= 1
    return [{"tp": tp[k], "fp": pred[k] - tp[k], "fn": gold[k] - tp[k]} for k in sorted(gold)]


def tally(disagreements: list[dict], decisions: dict[str, dict]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in ("system_only", "annotator_only"):
        rows = [r for r in disagreements if r["type"] == kind]
        verdicts = [decisions[item_id(r)]["decision"] for r in rows if item_id(r) in decisions]
        out[kind] = {"items": len(rows), "decided": len(verdicts), "in_scope": verdicts.count("yes"),
                     "not_in_scope": verdicts.count("no"), "unsure": verdicts.count("unk")}
    return out


def report(per_paper: list[dict], disagreements: list[dict], decisions: dict[str, dict], reps: int = 2000) -> dict[str, Any]:
    base = [{"tp": p["tp"], "fp": p["pred"] - p["tp"], "fn": p["gold"] - p["tp"]} for p in sorted(per_paper, key=lambda p: p["pmcid"])]
    return {"as_scored": prf_ci(base, reps), "tally": tally(disagreements, decisions),
            "adjudicated": {pol: prf_ci(adjudicate(per_paper, disagreements, decisions, pol), reps) for pol in POLICIES}}
