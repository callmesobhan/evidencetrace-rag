"""Orchestration: ingest -> retrieve -> verify -> conflict-check -> decide -> answer.

The answer is *assembled* from verified Findings; nothing in this module generates free text that
contains numbers except by formatting a Finding's own fields.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from evidencetrace.abstention.policy import REASON_TEXT, decide
from evidencetrace.config import Config
from evidencetrace.errors import IngestError
from evidencetrace.extraction.extractor import extract_findings, make_tagger
from evidencetrace.extraction.fields import FieldTagger
from evidencetrace.ingest.document import Document
from evidencetrace.ingest.parsers import SUPPORTED, parse_file
from evidencetrace.retrieval.hybrid import ChunkRetriever, HybridRetriever
from evidencetrace.retrieval.lexical import Hit, LexicalFindingRetriever, Retriever
from evidencetrace.schemas import Answer, AnswerStatus, Attribution, Finding
from evidencetrace.store import Workspace
from evidencetrace.textnorm import tokenize
from evidencetrace.verification.conflicts import detect_conflicts, unassessed_pairs
from evidencetrace.verification.provenance import Verifier


@dataclass
class IngestReport:
    documents: int
    findings: int
    own: int
    cited: int


class EvidencePipeline:
    def __init__(
        self,
        workspace: Workspace | str | Path,
        config: Config | None = None,
        *,
        tagger: FieldTagger | None = None,
        chunk_retriever: ChunkRetriever | None = None,
    ) -> None:
        self.ws = workspace if isinstance(workspace, Workspace) else Workspace(workspace)
        self.cfg = config or Config()
        self._tagger = tagger
        self._chunk_retriever = chunk_retriever

    # ------------------------------------------------------------------ ingest
    def ingest_paths(self, paths: Iterable[str | Path]) -> IngestReport:
        files: list[Path] = []
        for p in map(Path, paths):
            files += sorted(q for q in p.rglob("*") if q.suffix.lower() in SUPPORTED) if p.is_dir() else [p]
        return self.ingest_documents(parse_file(f) for f in files)

    def ingest_documents(self, docs: Iterable[Document]) -> IngestReport:
        tagger = self._tagger or make_tagger(self.cfg.extraction)
        n_docs, findings = 0, []
        ids: list[str] = []
        parsed: list[Document] = []
        for doc in docs:
            if doc.doc_id in ids:
                raise IngestError(f"two inputs map to the document id {doc.doc_id!r} (same file name stem, e.g. a.txt and "
                                  f"a.xml, or names that differ only in punctuation); rename one so each paper has its own id")
            findings += extract_findings(doc, tagger)
            ids.append(doc.doc_id)
            parsed.append(doc)
            n_docs += 1
        for doc in parsed:  # nothing is written until every input has parsed and extracted
            self.ws.save_document(doc)
        self.ws.replace_findings(ids, findings)
        cited = sum(f.attribution is Attribution.CITED for f in findings)
        return IngestReport(n_docs, len(findings), len(findings) - cited, cited)

    # --------------------------------------------------------------------- ask
    def _retriever(self, findings: list[Finding], docs: dict[str, Document]) -> Retriever:
        lexical = LexicalFindingRetriever(
            findings,
            rare_fraction=self.cfg.retrieval.rare_df_fraction,
            rarity_unit=self.cfg.retrieval.rarity_unit,
        )
        if self.cfg.retrieval.backend == "lexical":
            return lexical
        if self.cfg.retrieval.backend == "hybrid":
            chunks = self._chunk_retriever
            if chunks is None:
                from evidencetrace.retrieval.llama_index_store import LlamaIndexChunkIndex

                chunks = LlamaIndexChunkIndex(
                    docs,
                    model_name=self.cfg.retrieval.dense_model,
                    chunk_chars=self.cfg.retrieval.chunk_chars,
                    persist_dir=self.ws.index_dir,
                )
            return HybridRetriever(lexical, chunks)
        raise ValueError(f"unknown retrieval backend {self.cfg.retrieval.backend!r}")

    def ask(self, query: str) -> Answer:
        cfg = self.cfg
        docs = self.ws.load_documents()
        findings = self.ws.load_findings()
        if not cfg.retrieval.include_cited:
            findings = [f for f in findings if f.attribution is Attribution.OWN]

        hits = self._retriever(findings, docs).retrieve(query, cfg.retrieval.top_k)
        relevant = [
            h for h in hits
            if h.coverage >= cfg.abstention.min_coverage and len(h.missing_rare) <= cfg.abstention.max_missing_rare
        ]
        verifier = Verifier(docs, cfg.verification)
        verified = [h for h in relevant if verifier.verify(h.finding).ok]
        confident = [h for h in verified if h.finding.confidence >= cfg.abstention.min_confidence]
        kept = [h.finding for h in confident]
        conflicts = detect_conflicts(kept, cfg.conflicts)

        decision = decide(
            n_hits=len(hits),
            n_relevant=len(relevant),
            n_verified=len(verified),
            n_confident=len(confident),
            conflicts=conflicts,
            cfg=cfg.abstention,
        )
        confidence = _answer_confidence(verified or relevant)

        if decision.status is AnswerStatus.ABSTAINED:
            nearest = [h.finding for h in (relevant or hits)[:3]]
            why = "; ".join(REASON_TEXT[r] for r in decision.reasons)
            if hits and not relevant and hits[0].missing_rare:
                why += f" (the closest findings never mention: {', '.join(_as_written(query, hits[0].missing_rare))})"
            return Answer(
                query=query,
                status=decision.status,
                abstain_reasons=decision.reasons,
                nearest_evidence=nearest,
                confidence=confidence,
                summary=f"Abstained: {why}.",
            )
        n_docs = len({f.doc_id for f in kept})
        summary = f"{len(kept)} verified finding(s) from {n_docs} paper(s)."
        if conflicts:
            summary += f" {len(conflicts)} conflict(s) detected between them."
        caveats = []
        if (n := unassessed_pairs(kept, cfg.conflicts)) > 0:
            caveats.append(
                f"{n} pair(s) of findings could not be checked for conflicts because the "
                "intervention or outcome was not extracted for at least one of them."
            )
        return Answer(
            query=query,
            status=decision.status,
            findings=kept,
            conflicts=conflicts,
            caveats=caveats,
            confidence=confidence,
            summary=summary,
        )


def _as_written(query: str, stems: Iterable[str]) -> list[str]:
    """Show the user's own words, not the stems the index uses ("strok" -> "stroke")."""
    words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", query)
    return [next((w for w in words if s in tokenize(w)), s) for s in stems]


def _answer_confidence(hits: list[Hit]) -> float:
    """Extractor confidence x query coverage, over the best-supported hits. 0 if none."""
    if not hits:
        return 0.0
    return round(fmean(h.finding.confidence for h in hits) * fmean(h.coverage for h in hits), 4)
