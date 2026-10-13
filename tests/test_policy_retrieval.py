from evidencetrace.abstention import decide
from evidencetrace.config import AbstentionConfig
from evidencetrace.retrieval import ChunkHit, HybridRetriever, LexicalFindingRetriever
from evidencetrace.schemas import AbstainReason as R
from evidencetrace.schemas import AnswerStatus as S
from evidencetrace.schemas import Conflict, ConflictKind
from evidencetrace.textnorm import tokenize

CFG = AbstentionConfig()
CONFLICT = Conflict(kind=ConflictKind.DIRECTION, finding_a="a", finding_b="b", severity="high",
                    explanation="x")


def d(**kw):
    base = dict(n_hits=3, n_relevant=3, n_verified=3, n_confident=3, conflicts=[], cfg=CFG)
    return decide(**{**base, **kw})


def test_policy_ladder_reports_the_first_failing_stage():
    assert d(n_hits=0).reasons == [R.NO_RELEVANT_FINDINGS]
    assert d(n_relevant=0).reasons == [R.LOW_COVERAGE]
    assert d(n_verified=0).reasons == [R.UNVERIFIED_PROVENANCE]
    assert d(n_confident=0).reasons == [R.LOW_CONFIDENCE]
    assert d(n_confident=1, cfg=AbstentionConfig(min_verified=2)).reasons == [R.INSUFFICIENT_SUPPORT]


def test_policy_conflict_modes():
    assert d(conflicts=[CONFLICT]).status is S.CONFLICTING
    strict = AbstentionConfig(conflict_mode="abstain")
    out = d(conflicts=[CONFLICT], cfg=strict)
    assert out.status is S.ABSTAINED and out.reasons == [R.UNRESOLVED_CONFLICT]
    assert d().status is S.ANSWERED


def test_tokenize_synonyms_stems_and_stopwords():
    assert tokenize("Does Drug Zeta reduce BP?") == ["drug", "zeta", "blood", "pressur"]
    assert tokenize("hospitalization") == tokenize("hospitalisations") == tokenize("hospitalized")


def _findings(pipeline):
    return pipeline.ws.load_findings()


def test_relevant_query_has_full_coverage(pipeline):
    r = LexicalFindingRetriever(_findings(pipeline))
    top = r.retrieve("effect of Drug Zeta on systolic blood pressure", top_k=3)
    assert top[0].coverage == 1.0
    assert {h.finding.outcome for h in top if h.coverage >= 0.7} == {"systolic blood pressure"}


def test_unseen_rare_term_collapses_coverage(pipeline):
    r = LexicalFindingRetriever(_findings(pipeline))
    for q in ["Drug Zeta stroke", "Drug Zeta systolic blood pressure in children", "Drug Omega blood pressure"]:
        hits = r.retrieve(q, top_k=3)
        assert hits and max(h.coverage for h in hits) < 0.7, q


def test_hybrid_fuses_dense_chunks_but_keeps_lexical_coverage(pipeline):
    findings = _findings(pipeline)
    lex = LexicalFindingRetriever(findings)
    mi = next(f for f in findings if f.outcome == "myocardial infarction")

    class FakeChunks:
        def retrieve_chunks(self, query, k):
            # a dense hit on the chunk that contains the MI finding's sentence
            return [ChunkHit(mi.doc_id, mi.span.start - 10, mi.span.end + 10, 0.9)]

    hybrid = HybridRetriever(lex, FakeChunks())
    hits = hybrid.retrieve("Drug Omega myocardial infarction", top_k=3)
    assert hits[0].finding.finding_id == mi.finding_id
    assert hits[0].coverage == 1.0
    # dense-only evidence for an off-topic query must not manufacture coverage
    off = hybrid.retrieve("Drug Omega kidney failure", top_k=3)
    assert all(h.coverage < 0.7 for h in off)
