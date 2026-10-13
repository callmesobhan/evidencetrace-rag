"""On-disk workspace: canonical documents + extracted findings.

    <root>/docs/<doc_id>.json     canonical text, sections, sha256   (the source of truth for offsets)
    <root>/findings.jsonl         one Finding per line
    <root>/index/                 optional dense index (LlamaIndex persist dir)
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path

from evidencetrace.errors import IngestError
from evidencetrace.ingest.document import Document
from evidencetrace.schemas import Finding


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temporary file so a crash never leaves a half-written file behind."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Workspace:
    def __init__(self, root: str | Path, *, create: bool = True):
        self.root = Path(root)
        self.docs_dir = self.root / "docs"
        self.findings_path = self.root / "findings.jsonl"
        self.index_dir = self.root / "index"
        if create:
            self.docs_dir.mkdir(parents=True, exist_ok=True)

    def save_document(self, doc: Document) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", doc.doc_id) or doc.doc_id.startswith("."):
            raise IngestError(f"unsafe document id {doc.doc_id!r}: ids become file names (letters, digits, _ . -)")
        _atomic_write(self.docs_dir / f"{doc.doc_id}.json", doc.model_dump_json())

    def load_documents(self) -> dict[str, Document]:
        docs = {}
        for p in sorted(self.docs_dir.glob("*.json")) if self.docs_dir.exists() else []:
            doc = Document.model_validate_json(p.read_text(encoding="utf-8"))
            docs[doc.doc_id] = doc
        return docs

    def load_findings(self) -> list[Finding]:
        if not self.findings_path.exists():
            return []
        return [
            Finding.model_validate_json(line)
            for line in self.findings_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def replace_findings(self, doc_ids: Iterable[str], new: Iterable[Finding]) -> None:
        """Re-ingesting a document replaces *its* findings and leaves the others alone."""
        drop = set(doc_ids)
        kept = [f for f in self.load_findings() if f.doc_id not in drop]
        lines = [f.model_dump_json() for f in [*kept, *new]]
        _atomic_write(self.findings_path, "\n".join(lines) + ("\n" if lines else ""))
