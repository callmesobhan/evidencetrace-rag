# Architecture

## 1. The core idea: one trusted artifact, everything else is checked against it

```
              TRUSTED                                   UNTRUSTED (checked, never believed)
   ┌─────────────────────────────┐        ┌───────────────────────────────────────────────┐
   │ canonical text + sha256     │◄───────│ extractor (regex / BERT / future LLM)          │
   │ (textnorm.canonical_text)   │ verify │ retriever (BM25 / dense)                       │
   └─────────────────────────────┘        │ field tagger, confidence scores                │
                                          └───────────────────────────────────────────────┘
```

Every character offset in the system indexes into `Document.text`. `Document.sha256` pins the exact text
those offsets are valid for. Anything that claims "this number is at chars 628–760 of paper_a" can be
re-checked in one string slice. Changing `canonical_text()` invalidates every stored offset, which is why
it is isolated in one function and covered by the hash check.

## 2. Pipeline stages

| # | Stage | Module | Input → output | Deterministic? |
|---|---|---|---|---|
| 1 | Parse | `ingest/parsers.py` | file → `Document` (canonical text, sections, sha256) | yes |
| 2 | Sentence spans | `ingest/sentences.py` | `Document` → `Sentence(start, end, text, section)` | yes |
| 3 | Numeric candidates | `extraction/candidates.py` | sentence → metric, value, CI, level, unit, p, n | yes |
| 4 | Field tagging | `extraction/fields.py`, `bert_tagger.py`, `clauses.py` | the estimate's clause → intervention / comparator / outcome / population + confidence | rules: yes · BERT: model |
| 5 | Assemble + attribute | `extraction/extractor.py` | candidates + fields → `Finding`; own/cited; dedupe abstract↔results | yes |
| 6 | Retrieve | `retrieval/lexical.py`, `hybrid.py`, `query.py` | query → `Hit(finding, score, coverage)`; indexes the estimate's *clause*, tracks reference arms | lexical: yes · dense: model |
| 7 | Verify | `verification/provenance.py` | finding + document → `VerificationResult` | yes |
| 8 | Conflicts | `verification/conflicts.py` | verified findings → `Conflict[]`, plus unassessable pairs | yes |
| 9 | Decide | `abstention/policy.py` | funnel counts + conflicts → status + reasons | yes |
| 10 | Assemble answer | `pipeline.py`, `render.py` | verified findings → `Answer` (templated text, no generation) | yes |

Only stages 4 and 6 (dense part) involve learned models, and both are fenced in by stages 7–9.

### The answer funnel

```
hits ──coverage≥τc──▶ relevant ──provenance ok──▶ verified ──confidence≥τf──▶ confident ──▶ policy
 │                       │                           │                          │
 └ none: NO_RELEVANT     └ none: LOW_COVERAGE        └ none: UNVERIFIED_        └ none: LOW_CONFIDENCE
   _FINDINGS                                           PROVENANCE                  < min_verified: INSUFFICIENT_SUPPORT
```

Each stage's survivors are counted, so an abstention names the *first* stage that emptied the funnel.

## 3. Data contracts (`schemas.py`)

- **`SourceSpan`** — `doc_id, start, end, text, section`. Half-open `[start, end)` into canonical text.
- **`Finding`** — `clause` (the part of the sentence that holds this estimate; retrieval indexes it instead of the whole sentence), `finding_id` (unique per document: includes the interval, repeats get a suffix), `metric, value, ci{low,high,level}, p_value+operator, n, unit`, the four fields,
  `attribution` (own | cited), `span`, `extractor`, `confidence`, `doc_sha256`.
- **`VerificationResult`** — a dict of named boolean checks. `ok` is "all true"; failures are listed by
  name so a failed answer is debuggable.
- **`Conflict`** — `kind` (direction | magnitude | significance), `severity`, both finding ids, and a
  human-readable explanation built from the findings' own fields.
- **`Answer`** — `status` (answered | conflicting | abstained), `findings`, `conflicts`,
  `abstain_reasons`, `nearest_evidence` (abstentions only, labelled "not an answer"), `caveats`,
  `confidence`.

## 4. Verification checks (stage 7)

| Check | Catches |
|---|---|
| `document_present`, `document_unchanged` | stale index, re-parsed/edited source (the hash is recomputed from `Document.text`) |
| `span_text_matches` | offsets that no longer point at the quoted text |
| `estimate_reproduced` | right number, wrong slot: re-reads the span with the candidate extractor and requires metric, value, interval and p-value (with operator) to match, so a swapped interval or flipped operator is caught even though every number is in the sentence |
| `value_in_span`, `ci_in_span`, `p_in_span`, `n_in_span` | extractor that rounds, flips a sign, or invents a number |
| `intervention_in_span`, `outcome_in_span`, … | tagger output not grounded in the sentence |

Number matching is exact on parsed floats, with a sign counted only when it is not glued to a preceding
digit (so `0.65-0.93` is a range and `−10.1` is a negative), and scientific notation (`1.2 x 10^-5`, `3.1e-4`, `P<10-4`)
is read. None of this proves the sentence *supports* the claim: a number about another arm or outcome in the same
sentence passes. Optional semantic check: `NLIVerifier` (never run with real weights).

## 5. Conflict semantics (stage 8)

Two findings are *comparable* if they come from different papers, share a metric family (ratio vs
difference), and agree on intervention and outcome (and comparator when both state one) by token-Jaccard.
Ratios are compared on the log scale so HR 0.5 and HR 2.0 are symmetric about the null.

| Kind | Rule | Severity |
|---|---|---|
| `direction` | both significant, opposite sides of the null | high |
| `magnitude` | same metric, CIs do not overlap | medium |
| `significance` | CIs overlap, exactly one excludes the null | low |

Population mismatches are noted in the explanation rather than suppressing the conflict. If either
finding lacks intervention/outcome, the pair is *unassessable*: it is counted and reported in
`Answer.caveats` instead of silently passing.

## 6. Failure modes and how they are contained

| Failure | Contained by | Residual risk |
|---|---|---|
| Extractor misreads/rounds a number | `value_in_span` etc. | extractor picks the *wrong* number that is present in the sentence (eval: value/CI F1) |
| Right number, wrong claim (subgroup, negation) | optional `NLIVerifier` | without NLI this is undetected |
| Result is cited, not the paper's own | attribution heuristic: introduction, citation markers, and (in Discussion/Conclusion) no "our/we/this study" ⇒ cited; `include_cited=false` | 1.0% of "own" labels were another study's on the M1 test split (0.7%, 1 of 139, on unseen papers); 22% of "cited" labels were really own (the safe direction) |
| Topic match masquerading as an answer | coverage gate + **rare-term gate** (a finding lacking a rare query term is not relevant; rarity counted over papers, not findings, in the post-hoc config) | paraphrase → over-abstention (65-86% on real papers); roles are bound only heuristically (clause scoping, reference-arm tracking, "the most distinctive intervention word must be a subject"): the frozen system answered 88-94% of "effect of placebo on X" queries, the current code 0-11% (tuned on them) |
| Contradictory papers averaged away | conflict detection, `status=conflicting` | fields missing → unassessable pairs, reported as caveat |
| Source changed after indexing | `document_unchanged`, `span_text_matches` | none for text; PDF re-parse differences change the hash |
| LLM narrator invents a number (future) | planned number-guard: every numeral in the narration must exist in a verified Finding | not built yet |

## 7. Extension points

- `FieldTagger` (`tag(sentence) -> Fields`) — add a model-based tagger without touching anything else.
- `Retriever` / `ChunkRetriever` — swap lexical/dense/hybrid; coverage stays lexical unless you replace it.
- `Config` — all thresholds live in `configs/default.toml`; unknown keys are rejected.
- Metric registry — add a metric by extending `Metric` and `_METRIC_PATTERNS` (`candidates.py`).

## 8. Scale notes

Retrieval brute-forces BM25 over all findings (fine to ~10⁵). Beyond that, put an inverted index in front
of `LexicalFindingRetriever.score_index`. The dense index is persisted under `<workspace>/index/` and
rebuilt only when absent.

## 9. What real papers forced into the design (M1)

- **Sections come from the JATS structure**, never from guessed headings; tables/figures/LaTeX are dropped.
- **Numbers are parsed head + tail**: a metric/value head, then one of {labelled CI, bare bracketed CI, comma CI},
  then optional list continuation. Implausible readings are *dropped, not repaired*.
- **Within-paper abbreviation expansion** (`aliases`): search-only synonyms from the paper's own definitions.
- **`Finding.context`** (paper title) is stored but deliberately **not indexed**: indexing it made every finding in a
  paper an answer to any topic in its title.
- **Freeze discipline** is part of the architecture of the evaluation: `data/m1/FROZEN.json`, `frozen_snapshot/`.
