# Evaluation

A single end-to-end accuracy number cannot tell you *which stage* is wrong. This project scores five
things separately and treats abstention as a first-class quantity.

## 1. Metrics

### Extraction (`evaluation/runner.py::eval_extraction`)
- **Value+CI precision / recall / F1** — a predicted finding matches a gold finding if doc, metric, point
  estimate, and (when gold has one) CI bounds are equal. Greedy one-to-one matching.
- **p-value accuracy, n accuracy** — on matched pairs only.
- **Field token-F1** — for intervention / comparator / outcome / population, on matched pairs.
  Report the rule tagger and the BERT tagger side by side; this is where BERT should win.
- **Attribution accuracy** — own vs cited.

### Provenance (`eval_provenance`)
- **Verification pass rate** — share of *predicted* findings that pass all mechanical checks. With a
  rule extractor this should be ~1.0; with a BERT/LLM extractor it is a hallucination detector.
  Report `failed_checks` by name.
- **Span attribution accuracy** — a matched prediction is correctly attributed if its span contains the
  gold quote or has IoU ≥ 0.5 with it. (A finding can have the right number and the wrong sentence.)

### Conflicts (`eval_queries`)
- P/R/F1 over `(unordered pair of gold ids, kind)` tuples, overall and **by kind**. Predicted conflicts
  that involve an unmatched finding count as false positives.

### Abstention (`eval_queries`)
| Metric | Definition |
|---|---|
| **False-answer rate** | unanswerable queries that got an answer ÷ unanswerable queries. *The headline safety number.* |
| **Over-abstention rate** | answerable queries that were refused ÷ answerable queries. The price of safety. |
| Abstain P/R/F1 | abstention treated as a classification of "unanswerable" |
| **Coverage / selective accuracy** | share answered; accuracy among those |
| **Risk–coverage curve / AURC** | rank the *answered* queries by `Answer.confidence`, most-confident first; risk = error rate among those answered; an unanswerable query is an error whenever anything is produced, and a correct abstention is not an error (it only lowers coverage). Lower AURC = confidence is well ordered. (Before the red-team review the code scored correct abstentions as errors, which made AURC track the abstention rate; frozen M1 files keep that old figure.) |

Report false-answer rate **and** over-abstention rate together; either alone is trivially gamed.

## 2. Datasets

**Bundled (`data/samples/`)** — 5 synthetic papers, 8 gold findings, 9 queries. Purpose: regression
guard and a worked example of the gold format. Gold and corpus were written together, so scores here say
nothing about real-world accuracy.

**Public data to use for real numbers** (check each licence/availability before relying on it):

| Resource | Use here |
|---|---|
| Evidence Inference 2.0 (Lehman et al.; DeYoung et al.) | (intervention, comparator, outcome) → direction of effect + evidence span; fits field tagging and span attribution |
| EBM-NLP (Nye et al., 2018) | PICO span annotations for fine-tuning/evaluating the BERT tagger |
| SciFact (Wadden et al., 2020) | claim verification with SUPPORTS / REFUTES / NOT ENOUGH INFO — the NEI class is an abstention test |
| PubMedQA (Jin et al., 2019) | yes/no/maybe biomedical QA; useful as a sanity check, not for provenance |
| MS² (DeYoung et al., 2021) | multi-document medical-study summarisation; a source of studies that disagree |

None of these annotate *numeric* effect sizes with exact spans for the full pipeline, so plan to
annotate your own set (below).

## 3. Annotation protocol for the project's own gold set

1. Sample ≥ 150 Results/Abstract sentences containing an effect estimate from open-access papers (PMC OA).
2. Annotate per sentence: metric, value, CI (+level), p (+operator), n, the four fields, and own/cited.
   The *quote* is a distinctive substring; offsets are resolved by the loader.
3. For each topic with ≥ 2 papers, annotate comparable pairs and the conflict kind. Include pairs that are
   comparable-but-consistent as explicit negatives.
4. Write unanswerable queries of four types: *outcome never reported*, *outcome only in a figure/table*,
   *right topic wrong intervention*, *right topic wrong population*.
5. Double-annotate 20 %; report Cohen's κ for conflict labels and token-F1 agreement for fields.
6. Freeze a **held-out** split before tuning any threshold (`min_coverage`, `min_confidence`).

## 4. Ablations to run (each is one config flag)

| Ablation | Question it answers |
|---|---|
| `tagger = rules` vs `bert` | does BERT improve field F1, and does that move conflict F1? |
| `backend = lexical` vs `hybrid` | does dense retrieval recover paraphrases without raising false-answer rate? |
| verification off | how many wrong numbers would have reached the user? |
| coverage gate off | what does "nearest topic match" cost in false answers? |
| `include_cited = true` | how often are cited numbers presented as the paper's own? |
| `conflict_mode = abstain` vs `report` | is reporting a conflict better than refusing? |

## 5. Reporting rules

- Always show per-stage numbers, not just end-to-end.
- Put a bootstrap CI on every metric computed on < 500 items.
- Tune thresholds on dev, report on test; show the risk–coverage curve, not one operating point.
- Keep a failure gallery: for every missed/spurious finding and wrong status, the sentence and the stage.

## 6. Running it

```bash
make eval                                   # bundled smoke set -> reports/eval.{md,json}
evidencetrace eval --corpus <papers/> --gold <dir with gold_findings.jsonl + gold_queries.jsonl> \
                   --config configs/default.toml --out reports/
```

`gold_findings.jsonl` and `gold_queries.jsonl` formats: see `evaluation/gold.py` and the files in
`data/samples/gold/`.

## 7. The M1 protocol (real papers)

Implemented in `evaluation/m1.py`, `evaluation/m1_queries.py`, `scripts/{make_candidates,build_gold,make_queries,run_m1}.py`;
results and caveats in [m1-report.md](m1-report.md). The parts worth reusing:

- **Split first, by hash of the paper id**, before any tuning; **freeze** code + config and record a hash; keep a snapshot
  that reproduces the reported numbers byte-for-byte.
- **Two audits per split**: *precision* (review every prediction, pre-filled in gold format) and *recall* (review every
  sentence that looks statistical but produced nothing - independent of what the system predicted). Scope limits are
  tallied from the second list instead of being hand-waved.
- **Cluster bootstrap over papers** for extraction metrics (findings in one paper are not independent), over queries
  for abstention.
- **Unanswerable queries are constructed to be provably absent** (cross-paper pairs with no co-mentioning sentence;
  outcomes absent from the whole corpus) and **audited for label errors afterwards**: 1 of 43 test queries was
  mislabelled and the system was right (only answered unanswerable queries were audited). Caveats: *absent* queries cannot
  fail by construction, so report the *cross* queries separately; cross queries exclude drug+outcome co-occurring in one
  sentence, i.e. the hard negatives; report exact (Clopper-Pearson) intervals, not bootstrap percentiles, for rare events.
- **Split by study design.** Do not assume the corpus is what the query asked for: classify each paper from PubMed's publication
  types plus explicit title phrases (`ingest/design.py`), keep both signals, and report metrics for confirmed trials and for the rest.
- **Include hard negatives.** Unanswerable queries whose words all occur together ("effect of placebo on X") test role binding; queries whose
  words never co-occur (cross, absent) do not. Keep a set that was not used to develop the fix.
- **Report the leak rate** (another study's number labelled "own") as its own metric; it is the error this system exists
  to prevent.
- **Keep paraphrases and annotated wording separate**: they measure different things (recall of the relevance gate vs
  ability to answer when vocabulary matches).
