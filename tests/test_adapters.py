"""Model-backed adapters, tested through injected fakes (BERT/NLI) or mock embeddings (LlamaIndex)."""

import pytest

from evidencetrace.config import Config
from evidencetrace.extraction.bert_tagger import BertFieldTagger
from evidencetrace.pipeline import EvidencePipeline
from evidencetrace.schemas import AnswerStatus
from evidencetrace.verification.entailment import NLIVerifier, claim_text
from helpers import make_finding


def test_bert_tagger_postprocessing_with_fake_pipeline():
    sentence = "Drug Zeta reduced hospitalization compared with placebo."
    calls = []

    def fake_pipe(text):
        calls.append(text)
        return [
            {"entity_group": "INT", "word": "drug zeta", "score": 0.98, "start": 0, "end": 9},
            {"entity_group": "OUT", "word": "hospitalisation", "score": 0.91, "start": 18, "end": 33},
            {"entity_group": "CMP", "word": "placebo", "score": 0.95, "start": 48, "end": 55},
            {"entity_group": "OUT", "word": "compared", "score": 0.40, "start": 34, "end": 42},  # low score
            {"entity_group": "XXX", "word": "?", "score": 0.99, "start": 0, "end": 1},            # unknown
        ]

    fields = BertFieldTagger(pipe=fake_pipe).tag(sentence)
    # text is copied from the sentence by offsets, not from the model's detokenised `word`
    assert (fields.intervention, fields.outcome, fields.comparator) == (
        "Drug Zeta", "hospitalization", "placebo",
    )
    assert fields.population is None and 0 < fields.confidence <= 1
    assert calls == [sentence]


def test_bert_tagger_requires_a_model_or_pipe():
    with pytest.raises(ValueError):
        BertFieldTagger()


def test_bert_tagger_plugs_into_the_pipeline(tmp_path, samples):
    def fake_pipe(text):
        return []  # a tagger that finds nothing

    pipe = EvidencePipeline(tmp_path / "ws", tagger=BertFieldTagger(pipe=fake_pipe))
    pipe.ingest_paths([samples / "papers"])
    findings = pipe.ws.load_findings()
    assert findings and all(f.intervention is None for f in findings)
    # Numbers still verify and the sentence text still retrieves, but with no intervention/outcome
    # the opposing hospitalization results can't be compared. That must be said out loud rather
    # than reported as a clean answer.
    ans = pipe.ask("Does Drug Zeta reduce hospitalization?")
    assert ans.status is AnswerStatus.ANSWERED and len(ans.findings) == 2
    assert ans.conflicts == []
    assert any("could not be checked for conflicts" in c for c in ans.caveats)


def test_nli_verifier_with_fake_classifier():
    f = make_finding()
    yes = NLIVerifier(classifier=lambda x: [{"label": "entailment", "score": 0.93},
                                            {"label": "neutral", "score": 0.05}])
    no = NLIVerifier(classifier=lambda x: [[{"label": "contradiction", "score": 0.9},
                                            {"label": "entailment", "score": 0.02}]])
    assert yes.entails(f) and not no.entails(f)
    assert "Drug Zeta" in claim_text(f) and "placebo" in claim_text(f)


def test_llamaindex_chunk_index_and_hybrid_pipeline(tmp_path, samples):
    pytest.importorskip("llama_index.core")
    from llama_index.core.embeddings import MockEmbedding

    from evidencetrace.retrieval.llama_index_store import LlamaIndexChunkIndex

    cfg = Config()
    cfg.retrieval.backend = "hybrid"
    lexical_pipe = EvidencePipeline(tmp_path / "ws", cfg)
    lexical_pipe.ingest_paths([samples / "papers"])
    docs = lexical_pipe.ws.load_documents()

    index = LlamaIndexChunkIndex(
        docs, embed_model=MockEmbedding(embed_dim=8), chunk_chars=400, persist_dir=tmp_path / "idx"
    )
    hits = index.retrieve_chunks("Drug Zeta hospitalization", 5)
    assert hits
    for h in hits:  # node offsets come from OUR chunker and index the canonical text
        assert 0 <= h.start < h.end <= len(docs[h.doc_id].text)

    reloaded = LlamaIndexChunkIndex(
        docs, embed_model=MockEmbedding(embed_dim=8), persist_dir=tmp_path / "idx"
    )
    assert len(reloaded.retrieve_chunks("Drug Zeta", 5)) == len(index.retrieve_chunks("Drug Zeta", 5))

    pipe = EvidencePipeline(tmp_path / "ws", cfg, chunk_retriever=index)
    assert pipe.ask("Does Drug Zeta reduce hospitalization?").status is AnswerStatus.CONFLICTING
    assert pipe.ask("What is the effect of Drug Zeta on stroke?").status is AnswerStatus.ABSTAINED
