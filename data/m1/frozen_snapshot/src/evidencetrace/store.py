"""On-disk workspace: canonical documents + extracted findings.

    <root>/docs/<doc_id>.json     canonical text, sections, sha256   (the source of truth for offsets)
    <root>/findings.jsonl         one Finding per line
    <root>/index/                 optional dense index (LlamaIndex persist dir)
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from evidencetrace.ingest.document import Document
from evidencetrace.schemas import Finding


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.docs_dir = self.root / "docs"
        self.findings_path = self.root / "findings.jsonl"
        self.index_dir = self.root / "index"
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    def save_document(self, doc: Document) -> None:
        (self.docs_dir / f"{doc.doc_id}.json").write_text(doc.model_dump_json(), encoding="utf-8")

    def load_documents(self) -> dict[str, Document]:
        docs = {}
        for p in sorted(self.docs_dir.glob("*.json")):
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
        self.findings_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
