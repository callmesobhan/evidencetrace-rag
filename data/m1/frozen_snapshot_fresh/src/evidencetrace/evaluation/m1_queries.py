"""Query generation and abstention evaluation on the real M1 corpus.

Answerable queries come from field-annotated gold findings. Unanswerable queries are *constructed to
be provably absent* from the split:

  cross   intervention from paper A + outcome from paper B, kept only if NO sentence in the split
          mentions both (all content tokens of each side)
  absent  a real intervention + an outcome that appears nowhere in the whole raw corpus

Two answerable styles are scored separately because they answer different questions:

  annotated    wording copied from the paper: "can the system answer when vocabulary matches?"
  paraphrase  hand-written rewording: "what does the lexical coverage gate cost in recall?"
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path
from statistics import fmean
from typing import Any

from evidencetrace.config import Config
from evidencetrace.evaluation.gold import GoldFinding, load_gold_findings
from evidencetrace.evaluation.m1 import cluster_bootstrap, load_split
from evidencetrace.evaluation.metrics import aurc, match_findings
from evidencetrace.ingest.document import Document
from evidencetrace.ingest.sentences import split_sentences
from evidencetrace.pipeline import EvidencePipeline
from evidencetrace.schemas import AnswerStatus
from evidencetrace.textnorm import tokenize

GENERIC = {
    "intervention", "intervention group", "experimental group", "control group", "usual care",
    "placebo", "e2 intervention",
}  # fmt: skip
# Plausible clinical outcomes; each is kept only if it occurs nowhere in the raw corpus.
ABSENT_OUTCOME_POOL = [
    "hip fracture", "migraine frequency", "kidney stones", "osteoporosis", "glaucoma", "tinnitus",
    "cataract surgery", "psoriasis", "pancreatitis", "gout flares", "sleep apnea severity",
    "bone mineral density", "venous thromboembolism", "erectile dysfunction", "hair loss",
    "knee pain", "asthma exacerbations", "peripheral neuropathy",
]  # fmt: skip


def _specific(g: GoldFinding) -> bool:
    return bool(g.fields_annotated and g.intervention and g.outcome and g.intervention.lower() not in GENERIC)


def _in_one_sentence(docs: dict[str, Document], a: str, b: str) -> bool:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    for d in docs.values():
        for s in split_sentences(d):
            toks = set(tokenize(s.text))
            if ta <= toks and tb <= toks:
                return True
    return False


def build_queries(
    gold: list[GoldFinding],
    docs: dict[str, Document],
    corpus_text: str,
    paraphrases: dict[str, str],
    *,
    split: str,
    seed: int = 13,
    n_absent: int = 14,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    seeds = sorted((g for g in gold if _specific(g)), key=lambda g: g.gold_id)
    out: list[dict[str, Any]] = []

    def add(kind: str, query: str, expected: str, target: str | None) -> None:
        out.append({"qid": f"{split}-q{len(out) + 1:03d}", "split": split, "kind": kind, "query": query,
                    "expected": expected, "target": target})

    for g in seeds:
        add("annotated", f"What is the effect of {g.intervention} on {g.outcome}?", "answerable", g.gold_id)
        if g.gold_id in paraphrases:
            add("paraphrase", paraphrases[g.gold_id], "answerable", g.gold_id)

    for g in seeds:  # cross
        others = [h for h in seeds if h.doc_id != g.doc_id]
        rng.shuffle(others)
        for h in others:
            if not _in_one_sentence(docs, g.intervention or "", h.outcome or ""):
                add("cross", f"What is the effect of {g.intervention} on {h.outcome}?", "unanswerable", None)
                break

    lower = corpus_text.lower()
    absent = [o for o in ABSENT_OUTCOME_POOL if o.lower() not in lower]
    interventions = sorted({g.intervention for g in seeds if g.intervention})
    for _ in range(n_absent):
        add("absent", f"What is the effect of {rng.choice(interventions)} on {rng.choice(absent)}?",
            "unanswerable", None)
    return out


def _mean_ci(values: list[float], reps: int) -> tuple[float | None, float | None, float | None]:
    clusters = [{"v": v} for v in values]
    return cluster_bootstrap(clusters, lambda cs: fmean(c["v"] for c in cs) if cs else None, reps=reps)


def run_queries(
    raw: Path,
    split: str,
    gold_dir: Path,
    queries_path: Path,
    cfg: Config | None = None,
    *,
    reps: int = 2000,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    cfg = cfg or Config()
    docs = load_split(raw, split)
    gold = load_gold_findings(gold_dir / f"{split}_gold_findings.jsonl", docs)
    queries = [json.loads(ln) for ln in queries_path.read_text().splitlines() if ln.strip()]
    queries = [q for q in queries if q["qid"] not in (exclude or set())]  # audited label errors
    with tempfile.TemporaryDirectory() as tmp:
        pipe = EvidencePipeline(Path(tmp) / "ws", cfg)
        pipe.ingest_documents(docs.values())
        pred = pipe.ws.load_findings()
        mapping = match_findings(pred, gold)
        answers = [(q, pipe.ask(q["query"])) for q in queries]

    rows, rc_items = [], []
    for q, ans in answers:
        answered = ans.status is not AnswerStatus.ABSTAINED
        returned = {mapping.get(f.finding_id) for f in ans.findings}
        hit = q["target"] in returned if q["target"] else None
        correct = (answered and bool(hit)) if q["expected"] == "answerable" else (not answered)
        rows.append({**q, "status": ans.status.value, "answered": answered, "hit": hit, "correct": correct,
                     "n_findings": len(ans.findings), "confidence": ans.confidence,
                     "reasons": [r.value for r in ans.abstain_reasons],
                     "conflicts": len(ans.conflicts), "caveats": len(ans.caveats)})
        rc_items.append((ans.confidence if answered or ans.confidence else 0.0, correct and answered))

    def sel(kind: str | None = None, expected: str | None = None) -> list[dict]:
        return [r for r in rows if (kind is None or r["kind"] == kind) and (expected is None or r["expected"] == expected)]

    answerable, unanswerable = sel(expected="answerable"), sel(expected="unanswerable")
    report: dict[str, Any] = {
        "split": split,
        "queries": {k: len(sel(k)) for k in ("annotated", "paraphrase", "cross", "absent")},
        "answerable": {
            "n": len(answerable),
            "over_abstention_rate": _mean_ci([float(not r["answered"]) for r in answerable], reps),
            "hit_rate": _mean_ci([float(bool(r["hit"])) for r in answerable], reps),
            **{
                f"{k}_over_abstention": _mean_ci([float(not r["answered"]) for r in sel(k)], reps)
                for k in ("annotated", "paraphrase")
                if sel(k)
            },
            "mean_findings_returned": fmean(r["n_findings"] for r in answerable if r["answered"]) if any(r["answered"] for r in answerable) else None,
        },
        "unanswerable": {
            "n": len(unanswerable),
            "false_answer_rate": _mean_ci([float(r["answered"]) for r in unanswerable], reps),
            **{
                f"{k}_false_answer": _mean_ci([float(r["answered"]) for r in sel(k)], reps)
                for k in ("cross", "absent")
                if sel(k)
            },
        },
        "aurc": aurc(rc_items),
        "conflicts_reported": sum(r["conflicts"] for r in rows),
        "answers_with_unassessed_pairs": sum(r["caveats"] > 0 for r in rows),
        "per_query": rows,
    }
    return report
