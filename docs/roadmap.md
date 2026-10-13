# Roadmap

Ordered by what de-risks the project fastest. Each milestone has an exit test.

## M0 — Skeleton (done)
Deterministic core, synthetic corpus, per-stage evaluation, CI-able tests.
**Exit:** `make test` and `make eval` green on a clean checkout.

## M1 - Real data, real baseline (done; see [m1-report.md](m1-report.md))
111 CC BY PMC papers (only 67 are PubMed-confirmed trials; extraction accuracy is the same for the rest), deterministic dev/test split, 482 + 360 gold findings,
85 + 86 queries, frozen-code protocol with a byte-reproducible snapshot. **Outcome:** held-out F1 0.957 against one LLM
annotator (0.742 on 30 unseen papers annotated blind: 0.902 cardiometabolic, 0.477 other domains), 1.0% own/cited leak,
7.0% false answers (3 of 43; exact upper bound 19%), 35% over-abstention, 0 conflicts detected. **What it changed:** structure-aware JATS parsing, a rewritten numeric layer,
the rare-term gate, abbreviation expansion, verifier fixes, and a corrected plan for M2/M3 below.
**Still owed from M1:** a *human* annotator. An LLM-agent blind annotation of 36 papers is done
(`data/m1/independent/`), but every annotation in the repo is still LLM-made. Done since: study-design screening and
stratified metrics, hard-negative queries, role-aware retrieval, the covariate-balance filter, a clean 25-paper holdout
(out-of-sample F1 0.823), a review page for the disagreements, a tested PDF parser. Still owed: a human adjudication
(`docs/adjudication.html`), a hard-negative set not used to develop the retrieval fix, and a third unseen set before any further
extractor change.

## M2 — Learned field tagger  *(the bottleneck M1 identified)*
- Bootstrap training data from the rule tagger's high-confidence outputs, then correct by hand
  (silver → gold). Fine-tune with `scripts/train_field_tagger.py` (SciBERT / BiomedBERT-style base).
- Add EBM-NLP / Evidence Inference for pre-training.
- **Inherit the paper's primary intervention** from title/abstract when a Results sentence names none (4 of 29 test
  queries refused for exactly this reason).
- Filter covariate-balance SMDs (8 of 13 test false positives).
**Exit:** BERT beats rules on field token-F1 (today: intervention 0.17, outcome 0.06) *and* detects conflicts on real
papers (today: 0); verification pass rate stays >= 0.99; paper-level rarity re-validated on fresh papers; recall on
non-cardiometabolic papers (today 0.365) measurably up.

## M3 — Better relevance and abstention
- Replace the lexical coverage gate with a cross-encoder / NLI relevance score, keeping lexical as a floor.
- Concept normalisation (MeSH/UMLS) instead of the seed synonym list.
- Calibrate `Answer.confidence` (isotonic / Platt on dev) so risk–coverage is meaningful across corpora.
Target: today 65-86% of hand-written paraphrases are refused.
**Exit:** paraphrase over-abstention falls substantially with the false-answer rate no worse than today's (3 of 43; exact upper bound 19%) and hard-negative queries added.

## M4 — Beyond sentences
- Table extraction (the most common home of effect sizes), forest-plot captions, subgroup rows.
- Cross-sentence candidates ("The primary outcome … HR 0.78. … (95% CI …)").
- Same-paper multi-arm and subgroup handling in conflict detection.
**Exit:** recall on table-only results; no regression in provenance pass rate.

## M5 — Claims and narration
- *Claim mode:* "Does X reduce Y by ~20 %?" → supported / contradicted / not enough evidence, with the
  matching findings (SciFact-style).
- Optional LLM narrator that paraphrases the structured answer under a **number guard**: every numeral in
  the narration must appear in a verified Finding, else fall back to the template.
**Exit:** zero unguarded numerals in an adversarial test set.

## M6 — Productisation
- Pre-built embeddings/index per corpus, incremental ingest, web UI with span highlighting
  (`evidencetrace inspect` is the prototype), API server, licence selection, CI badges.

## Open questions
- How should conflicts be summarised for a clinician: pairwise (now) or as a small pooled/forest view?
  (Pooling is deliberately **not** done — it needs study-level risk-of-bias and heterogeneity judgement.)
- Is `significance` (low severity) useful, or noise, to real users? Needs user study in M1.
