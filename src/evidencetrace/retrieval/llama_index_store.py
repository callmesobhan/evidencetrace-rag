"""LlamaIndex-backed dense chunk index.

We build the ``TextNode`` objects ourselves from our own sentence-aligned chunks, with
``start_char_idx`` / ``end_char_idx`` set from the canonical text. LlamaIndex therefore never
decides where a chunk begins, and a retrieved node maps back to findings by plain offset containment.

Requires the `llama` extra. Pass ``embed_model`` to inject any LlamaIndex embedding (tests use
``MockEmbedding``); otherwise a HuggingFace embedding named by ``[retrieval] dense_model`` is used.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from evidencetrace.ingest.chunking import chunk_document
from evidencetrace.ingest.document import Document
from evidencetrace.retrieval.hybrid import ChunkHit


class LlamaIndexChunkIndex:
    def __init__(
        self,
        docs: Mapping[str, Document],
        *,
        embed_model: Any = None,
        model_name: str = "BAAI/bge-small-en-v1.5",
        chunk_chars: int = 1200,
        persist_dir: str | Path | None = None,
    ) -> None:
        from llama_index.core import StorageContext, VectorStoreIndex, load_index_from_storage
        from llama_index.core.schema import TextNode

        if embed_model is None:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            embed_model = HuggingFaceEmbedding(model_name=model_name)

        persist = Path(persist_dir) if persist_dir else None
        if persist and (persist / "docstore.json").exists():
            storage = StorageContext.from_defaults(persist_dir=str(persist))
            self._index = load_index_from_storage(storage, embed_model=embed_model)
            return

        nodes = []
        for doc in docs.values():
            for ch in chunk_document(doc, max_chars=chunk_chars):
                nodes.append(
                    TextNode(
                        id_=ch.chunk_id,
                        text=ch.text,
                        start_char_idx=ch.start,
                        end_char_idx=ch.end,
                        metadata={"doc_id": ch.doc_id, "start": ch.start, "end": ch.end,
                                  "section": ch.section},
                        # offsets/ids are bookkeeping; they must not leak into the embedding
                        excluded_embed_metadata_keys=["doc_id", "start", "end", "section"],
                        excluded_llm_metadata_keys=["start", "end"],
                    )
                )
        self._index = VectorStoreIndex(nodes, embed_model=embed_model)
        if persist:
            persist.mkdir(parents=True, exist_ok=True)
            self._index.storage_context.persist(persist_dir=str(persist))

    def retrieve_chunks(self, query: str, k: int) -> list[ChunkHit]:
        retriever = self._index.as_retriever(similarity_top_k=k)
        hits = []
        for nws in retriever.retrieve(query):
            md = nws.node.metadata
            hits.append(
                ChunkHit(md["doc_id"], int(md["start"]), int(md["end"]), float(nws.score or 0.0))
            )
        return hits
