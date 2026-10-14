# Known issues and limitations

Everything below was found by the author, by five blind annotator agents, by a clean-room reproducer, or by a
red-team reviewer, and is stated here instead of being left for a reader to discover. Items are grouped by what they
threaten: the *evidence* (can the numbers be trusted), the *system* (what it cannot do), the *bugs* that were found and
how they were handled, and the *reproduction* (can you get the same numbers). Section E lists each red-team finding
with its status.

Throughout, "agent" means an LLM instance with its own context. **The only human judgements in this repository are two adjudications of the system-vs-annotator disagreements**: the repository owner's
(all 158, by their own statement) and a second adjudicator's (a medical researcher who asked not to be named and reports no AI use; 69 clean-holdout items; kappa 0.43; the 12 disagreements are two unresolved scope rules).
See `data/m1/independent/adjudication/`. No human has verified the M1 gold, the annotators' matched estimates, the reviews or the numbers.
The reviewer, the annotators and the reproducer were agents.

## A. Threats to the evidence

| # | Issue | Consequence | Status |
|---|---|---|---|
| A1 | The M1 gold standard (111 papers) was produced by a single LLM that is also the developer of the extractor; the review sheets showed it the system's own confidence and attribution. | Every M1 figure is "agreement between the system and one reviewer", not accuracy. Judgements of what counts as an estimate drifted with the extractor's scope. | Partly addressed: the owner adjudicated the disagreements with the blind annotators (G5); the M1 gold itself still has no human check. |
| A2 | The independent check (`data/m1/independent/`) is also LLM agents: five annotators, 36 papers, one annotator per paper except the 6-paper overlap with the developer. | Independence of *context*, not human ground truth. Shared model blind spots are possible. Intervals are wide. | Partly addressed by the owner's adjudication of the disagreements (G5); the annotations themselves are still LLM-made. |
| A3 | Gold is pooled from the system's own output plus a near-miss audit. Dev precision 1.000 is by construction (0 rejected). | Precision is flattering; recall is an upper bound (estimates without a statistical cue are invisible). | Documented. |
| A4 | **The M1 test recall (0.950) did not generalise.** On 30 fresh papers annotated blind, the frozen system reaches recall 0.653 (F1 0.742): 0.874 / F1 0.902 on cardiometabolic papers, **0.365 / F1 0.477 on other domains**. | The headline M1 test F1 (0.957) describes cardiometabolic papers phrased the way the regexes were fitted to. Do not quote it as general accuracy. | Open. Fixes made afterwards raise the fresh F1 to 0.865, but they were made on those same papers: **not held-out**. A clean second round on 25 unseen papers gives F1 **0.823**; pooled with round 1, the frozen system scores **0.785 [0.707, 0.849]** on 55 unseen papers (A14). |
| A5 | Agreement papers: independent vs developer F1 is 0.648 (0.718 if `IRR` and `RR` are one metric). One paper (PMC12810801, 35 odds ratios written `COR/p = 6.30/0.01`) accounts for most of the difference. | Both the system and the developer's gold missed a notation the developer had never seen. | Not extracted (deliberately: one paper). Guidelines v1.1 rule such estimates in scope. |
| A6 | Post-hoc changes after the test split was scored (`rarity_unit = "papers"`, `%-` ranges, scientific-notation p-values), and post-review changes after the independent annotation and the review. | Post-hoc / post-review columns are not held-out. | Labelled everywhere; `FROZEN.json` lists every changed file. |
| A7 | One test query label was wrong (1 of 43); only answered unanswerable queries were audited. | The label error rate is unknown. | Corrected via `label_corrections.json`; corrected frozen figure is 2 / 42. |
| A8 | **The corpus is not "111 randomized trials".** PubMed (publication types) and explicit title phrases (`data/m1/design.jsonl`) show **67 confirmed trials** (42 of 63 dev, 25 of 48 test) and 44 others: 16 evidence syntheses, 8 observational, 3 protocols, 1 economic evaluation, 16 plain journal articles. PMC's `article_type` is `research-article` for all of them. 3 papers (2 test, 1 fresh) have conflicting PubMed and title signals and need a human read. | Wording corrected everywhere. **Extraction accuracy is the same for both groups** (test F1 0.956 for confirmed trials, 0.980 for the rest; intervals overlap), so the extraction numbers stand. One esaxerenone meta-analysis is 37 of 310 own test findings and the source of all 3 frozen test false answers; the abstention queries were not split by design. | Screened and stratified (`make design by-design`); a human read of the 3 disagreements is open. |
| A9 | Small samples: 48 test papers, ~43 answerable and ~43 unanswerable queries per split. | A `[0, 0]` bootstrap interval on zero events is an artefact; exact upper bounds are 19.1% for 3 of 43 and 8.4% for 0 of 42. | Reported with exact bounds. |
| A10 | **The false-answer headline is weaker than it looks.** The 14 *absent* queries cannot fail (their outcome word has document frequency 0, which the rarity gate always refuses). Only the 29 *cross* queries test anything: 3 / 29 = 10.3% (exact upper 27.4%). They exclude drug+outcome co-occurring in one sentence, i.e. the hard negatives. The 3 failures are one drug from one paper, and one is a label error. | The 7.0% overstated the evidence for wrong-drug protection. **Measured now:** for "effect of placebo on X" the frozen system answered 15 / 17 (dev) and 17 / 18 (test). | Hard negatives added (`make hardneg`). The fix (B1) is tuned on them: a hard-negative set not used to develop it is open. |
| A11 | Several metrics cannot fail by construction: provenance pass rate (parser re-finds its own number), value+CI identical to value-only (sheets pre-filled with the interval), span attribution (short gold quote inside the predicted sentence), p/n accuracy (copied from predictions), dev precision, population token-F1 (`None == None` counted as agreement). | They are consistency checks, not accuracy. | Relabelled in the report; population F1 now excludes empty pairs. A blind annotator filling CI / p / n is open. |
| A12 | The same clinical trials sit on both sides of the split (EMPACT-MI: PMC11955319 dev, PMC11115458 test; DAPA-HF: PMC8247863 dev, PMC10234442 / PMC7664959 / PMC9508991 test). | A split by paper id is not a split by trial; test is not fully independent of dev. | Documented. |
| A13 | The held-out "freeze" is a convention: hashes prove files are unchanged since the record was written, not *when* they were frozen relative to the test annotation, and one party ran the whole procedure. | The freeze is auditable for consistency, not for timing. | Stated in `FROZEN.json` (`limits_of_this_record`). |
| A14 | **The extraction fixes made after round 1 are not shown to help on unseen papers.** The pre-fix and the post-review systems give *identical* predictions on the 25 clean-holdout papers (168 each); all 27 predictions added after round 1 fall in round-1 papers. | The round-1 gain (0.742 to 0.865) is a tuning effect. The recall gap outside cardiometabolic papers seen in round 1 (0.365) is not reproduced in round 2 (0.783, 10 papers); with these sample sizes it is neither confirmed nor refuted. | Documented. A third holdout is needed to test any further extractor change (needs new downloads). |

## B. What the system cannot do (yet)

| # | Issue | Evidence |
|---|---|---|
| B1 | **Retrieval binds roles only heuristically.** The frozen system answered "the effect of placebo on X" with a drug-vs-placebo contrast for 88-94% of hard negatives. Now findings carry the clause that holds the estimate, fields are tagged from it, reference-arm text and generic control words are tracked, and the most distinctive intervention word must be a subject: 0 / 17 dev and 2 / 18 test answered, with no change on answerable queries. | **Tuned on these queries**, so not an out-of-sample estimate. Still heuristic: `but` / `although` are not clause boundaries (elliptical subjects), a control word in another sense ("active control", "blood pressure control") leaks (the 2 test queries), a subgroup comparison inside the placebo arm is ambiguous, and "placebo on X" is refused by policy even where a sentence has placebo as its grammatical subject. |
| B2 | **Conflict detection is dormant on real text.** The rule field tagger fills any field for ~10% of findings, and conflicts need intervention and outcome on both sides. Also: ratio metrics of different kinds (HR vs OR) are compared on sign alone, `Interval.level` is ignored, and findings without an interval have confidence 0.45 < the 0.6 threshold so they are filtered before conflict detection. | 0 conflicts over 171 real-paper queries; tested on 5 synthetic papers only. |
| B3 | Lexical relevance gate refuses paraphrases. | 86% of hand-written paraphrases refused (35% of all answerable queries). The price of few false answers. |
| B4 | Unnamed estimates ("increased haemoglobin by 7.3 g/L (95% CI 6.2, 8.5)"), regression coefficients, rates, win ratios, tables and figures are out of scope. | About 5-15% of CI-bearing estimate sentences use no metric name. |
| B5 | The BERT tagger, NLI verifier and dense/hybrid retrieval have **never been run against real model weights** (the LlamaIndex index is tested with a mock embedding). The PDF parser has been tested on generated PDFs but not on real publisher PDFs (B13). The persisted dense index is now rebuilt when its documents, chunk size or embedding model change. | Treat as unverified code. |
| B6 | Attribution (own vs cited) is a lexical heuristic. | 22% of findings labelled "cited" were really own (the safe direction); 1 of 139 "own" labels on fresh papers and 3 of 310 on the M1 test split were another study's result. |
| B7 | Estimates in unusual notation (`COR/p = 6.30/0.01`) or with a reversed printed interval are not recognised. | Strict `xfail` test. |
| B8 | A heart rate written `HR 72 (95% CI 70-74)` with no unit or context word is read as a hazard ratio (units, "heart rate" / "beats" context and "RR interval" are guarded). | Strict `xfail` test. |
| B9 | ~~Covariate-balance SMDs are extracted as effects.~~ **Fixed:** an SMD with no interval and a balance cue (a proportion contrast, "prevalence", "baseline", "propensity", "weighting", "matched", "standardized difference") is not an effect. | The 8 test false positives (one paper) are gone and no true estimate in 166 papers is lost; written after seeing them, so test F1 0.967 vs the held-out 0.957 is post-hoc. An SMD without an interval and without a cue is still extracted. |
| B10 | Non-English text: decimal commas are rejected rather than parsed. | 2 Portuguese passages in the corpus. |
| B11 | `Answer.confidence` is a transparent heuristic, not a calibrated probability. | `extractor._confidence`, `pipeline._answer_confidence`. |
| B12 | The downloader drops a whole 20-paper batch if one paper contains an `<!ENTITY` declaration; dependencies have lower bounds only and there is no lockfile. | Minor. |
| B13 | **PDF parsing is tested on generated PDFs only.** A generated two-column journal-style PDF exposed four faults in the first version, all fixed with tests: line-end hyphen breaks left in the text (80 in one paper), running headers kept (9 copies), sentences cut by a column or page break losing their interval and p-value, and PyMuPDF's deprecated `fitz` import. A scanned PDF or a corrupt file is now a one-line error. Real publisher PDFs (tables, equations, footnotes, odd font encodings) are untested; tables are not parsed; a compound split at a line end ("long-" / "term") is joined as "longterm". | `tests/test_pdf.py` (the PDF tests need `pip install -e ".[pdf]"`; CI installs it). |

## C. Bugs found in the frozen extractor

| # | Bug | Effect on the published numbers |
|---|---|---|
| C1 | **Sign loss:** `difference of – 3.35 g/m2` (en or em dash, or a true minus after a filler phrase) was returned as +3.35, because the filler consumed the sign. | Found on a fresh paper. Diffing the frozen against the fixed extractor over all 111 M1 papers gives **zero sign-only differences** and no change on the test split, so no published M1 number is affected. The held-out fresh predictions still contain it and are kept unmodified on purpose. |
| C2 | `mean difference at week 52, -2.91; 95% CI ...` (number inside the filler), credible intervals (`CrI`), `LSMD`, Cohen's d / Hedges' g with a CI, `absolute difference in risk`. | Missed by the frozen extractor (recall loss on fresh papers). Fixed; regression tests. |
| C3 | A DOI fragment parsed as a risk ratio; within-arm changes parsed as mean differences. | False positives on fresh papers. Guards added. |
| C4 | Scientific-notation p-values: `p = 3.1e-4` read as 3.1, `1.2 x 10^-5` as 1.2, `P < 10-4` as 10 (and they verified, because those digits are in the sentence). | The frozen test output contains **two wrong p-values** of this kind (PMC9318947: `2.01 x 10-5` read as 2.01 and `1.02 x 10-6` as 1.02), which is why frozen p-value accuracy is 0.991 and current 0.997; the other forms (`e-4`, `^-5`, `P<10-4`) are the reviewer's probes and changed no M1 finding. Fixed; tests. |
| C5 | Lancet-style decimals `2·5` read as 2.0 (and verified). | None of the 166 corpus papers writes an estimate this way. Fixed (`canonical_text`); tests. |
| C6 | `finding_id` ignored the interval, so ids collided (frozen code: dev 464 findings / 461 ids, test 355 / 349). Consequences: `missed_gold` in the frozen results lists 24 (test) and 21 (dev) ids where the metrics count 18 and 18; the independent scorer, which keys by id, was slightly off on the tuned-on-fresh figure (0.871 reported, 0.865 correct). | Counts (tp / fp / fn) were unaffected; held-out independent figures were unaffected. Ids are now unique per document; the scorer keys by row. |
| C7 | Dedupe collapsed or kept findings by id; a naive fix (dedupe by identity) dropped a real finding, the same OR / CI printed for two arms of one sentence. | Caught by the test-split recall change during this work; fixed (restatements collapse across sentences only) and tested. |

The test split differs between the frozen and the current extractor in **zero** findings; dev differs in 8 (2 dropped,
6 added).

## D. Reproduction

| # | Issue | Status |
|---|---|---|
| D1 | The discovery fetch is not reproducible: PubMed's ranking and PMC's holdings change (a stranger who ran the old `make fetch` got 66 papers, 11 not in the pinned set). | Fixed: `make fetch-pinned` (exact PMCIDs, SHA-256 verified, drift reported); discovery renamed `make fetch-new`. |
| D2 | "Byte-identical" held only on Python 3.12+ (3.12 made float `sum()` compensated; one `aurc` value differed in its 16th digit on 3.11). | Fixed: result files round floats to 12 digits, `aurc` uses `math.fsum`. **Verified:** frozen and current results, held-out predictions and independent scores are byte-identical on Python 3.11.17 and 3.13.9. |
| D3 | `FROZEN.json` hashes could not be verified (undocumented algorithm; the recorded manifest hash was of a git-ignored file). | Fixed: `scripts/verify_freeze.py` and `tests/test_freeze.py` recompute every hash, plus 33 pinned evaluation files. |
| D4 | `PYTHONPATH=...frozen_snapshot/src python -I ...` silently ran the *current* code. | Fixed: `run_m1.py --frozen` refuses unless the frozen source is the one imported. |
| D5 | `make_queries.py` silently dropped paraphrases (and renumbered every query) when `--out` pointed to a new directory. | Fixed: `--paraphrases`, stable default; missing file is an error. |
| D6 | Make targets overwrote tracked result files. | Fixed: outputs go to `reports/` and are diffed. |
| D7 | The papers are downloaded, not committed. If PMC changes a paper's XML the pinned hash will not match. | `fetch --from-manifest` reports the drift and exits non-zero. |
| D8 | Licence: MIT is the default choice (only the copyright holder was specified). | The holder can change it. The quoted sentences in `data/m1/` keep their CC BY terms (`ATTRIBUTION.md`, generated from each paper's own metadata). |

## E. Red-team review: every finding and its status

An independent reviewer agent reproduced each item with a probe script. "Fixed" means a regression test was added
(`tests/test_review_fixes.py`), "Documented" means the limitation is stated and, where possible, recorded as a strict
`xfail` (`tests/test_known_limits.py`).

| Id | Sev. | Finding | Status |
|---|---|---|---|
| R-01 | blocker | Corpus is not 111 randomized trials. | Wording fixed everywhere; screening open (A8). |
| R-02 | blocker | "Trace" overclaimed: provenance checks presence in the sentence, not slot; hash never recomputed. | **Fixed**: positional `estimate_reproduced`, recomputed hash, corrected README / architecture wording. |
| R-03 | blocker | False-answer headline flattering (absent queries cannot fail; hard negatives excluded; bound not a bound). | Reworded with cross-only figure and exact bounds (A10); hard negatives open. |
| R-04 | major | Metrics that cannot fail. | Relabelled (A11). |
| R-05 | major | AURC counted correct abstentions as errors. | **Fixed** in code (answered-only); frozen files keep the old figure and say so. |
| R-06 | major | `finding_id` collisions; `missed_gold` lists wrong length. | **Fixed** (C6). |
| R-07 | major | Retrieval cannot bind roles. | Documented, `xfail` (B1). |
| R-08 | major | Middle-dot decimals read as integers. | **Fixed** (C5). |
| R-09 | major | Scientific-notation p-values wrong (and verified). | **Fixed** (C4). |
| R-10 | major | Same-stem files silently overwrite. | **Fixed**: duplicate ids are an error, nothing is written. |
| R-11 | major | Documented reproduction path was the non-reproducible fetch. | **Fixed** (D1). |
| R-12 | major | CC BY attribution incomplete (109 of 111, truncated titles, no authors / licence / indication of changes). | **Fixed**: generated for all 166 articles from JATS metadata, with a changes statement. |
| R-13 | minor | Freeze record inconsistent; hashes unverifiable. | **Fixed** (D3); timing limit stated (A13). |
| R-14 | minor | Same trials in both splits; anchoring; exact leak bound 2.8%. | Documented (A1, A12; exact bound in the report). |
| R-15 | minor | Quadratic regexes on long single lines. | **Mitigated**: 6000-character sentence cap (longest real sentence: 3,965), linear heading regex; test. |
| R-16 | minor | `HR` heart rate and `RR` interval accepted as ratios. | **Partly fixed**; the bare case is open (B8). |
| R-17 | minor | Conflict logic: `p<0.05`, units, MD vs SMD, ratio mixing, `level`, confidence filter. | `p<`, units and MD-vs-SMD **fixed**; the rest open (B2). |
| R-18 | minor | Results sections with back-matter words in the title dropped. | **Fixed**. |
| R-19 | minor | Local XML not hardened; raw tracebacks; non-atomic writes. | **Fixed**: entity declarations refused, nesting / encoding / syntax errors are one-line errors, writes are atomic and happen only after every input parsed. |
| R-20 | minor | Terminal-escape injection through quotes; unsafe doc ids as file names. | **Fixed**: control characters stripped in `canonical_text`; ids validated. |
| R-21 | minor | Persisted LlamaIndex index never invalidated. | Open (B5). |
| R-22 | minor | Unpinned dependencies / actions; scripts not linted. | CI permissions and script linting **fixed**; no lockfile (B12). |
| R-23 | minor | LICENSE had a note after the MIT text; no URLs / classifiers. | **Fixed**. |
| R-24 | minor | README overclaims (guarantees, components, confidence). | **Fixed**. |
| R-25 | minor | Misleading CLI / config behaviour; BOM. | **Fixed**; config types are checked. |
| R-26-R-34 | nit | Roadmap "upper bound" wording; stale data README; README layout; stem leak in abstention text; `.gitignore`; `µ` vs `μ` in the unit list; missing tests; README kept the mislabelled query. | **Fixed** (the report now shows the corrected 2 / 42). |

## F. Follow-up after publication: items 1-4 of the open list

| Item | What was done | Evidence | What it does not show |
|---|---|---|---|
| 1. Study-design screening | `ingest/design.py` + `scripts/fetch_design.py` classify each paper from PubMed publication types and explicit title phrases; `scripts/stratify_m1.py` scores extraction per group. | 67 of 111 confirmed trials; extraction F1 is 0.956 (trials) vs 0.980 (rest) on test. A first version had two bugs found by reading the output (a "Clinical Trial Protocol" counted as a trial; "pooled analysis" overriding PubMed's trial label); both fixed with tests built from the real cases. | The 16 untyped journal articles are *not confirmed* as trials, not proven non-trials (the ones read were observational, biomarker or guideline papers). The abstention queries were not split by design. |
| 2. Hard negatives | `build_hard_negatives` generates "effect of <reference arm> on X" queries from the gold (17 dev, 18 test); `scripts/eval_hardneg.py` scores any code version; `data/samples_hardneg` holds exact-label synthetic role swaps. | Frozen 15 / 17 and 17 / 18 answered; synthetic frozen false-answer rate 1.000. | Real annotations contain no sentence with two different interventions, so within-sentence swaps exist only in the synthetic set, which was written knowing the fix. "Reference arm as intervention" is a labelling judgement, stated in the code. |
| 3. Role binding | `extraction/clauses.py`, `retrieval/query.py`, role-aware scoring in `retrieval/lexical.py`; fields tagged from the clause. An intermediate version lost two answerable dev queries (a `;` that separates statistics was treated as a clause boundary) and was corrected; the final version changes no answerable-query result. | Hard negatives 0 / 17 and 2 / 18; over-abstention and hit rate unchanged (dev 36.4% / 61.4%, test 32.6% / 67.4%); the strict `xfail` for the reviewer's `whereas` example now passes. | Tuned on the hard negatives. Not evaluated on the 25 never-annotated fresh papers or on paraphrases written independently of the fix. |
| 4. Balance SMDs | `BALANCE_CONTEXT` guard in `extraction/candidates.py` (see B9). | 8 false positives removed, none lost; a first version let one of them through because its "A% vs B%" pattern handled only one-digit integers (caught by trying it on the real sentences; the final version was then run on all 166 papers). | Post-hoc on the test split. |

## G. Follow-up 2: items 5-9 of the open list (what was done without a human)

| Item | What was done | What it shows | What it does not show |
|---|---|---|---|
| 5. Human adjudication | `docs/adjudication.html` (served at the repository's GitHub Pages site) and `scripts/apply_adjudication.py`. The owner's export (161 verdicts, all decided) is in `data/m1/independent/adjudication/`; applying it moves the frozen system's pooled F1 on 55 unseen papers from 0.785 to 0.837 [0.786, 0.884] (annotators over-included 22 of 129; 17 of 29 system-only items were real estimates). | The annotator-as-truth scores understate the system, and the two rounds agree once adjudicated (0.834 vs 0.839). | Single adjudicator, the repository owner (by their own statement; qualifications not recorded; no inter-rater statistic). Only disagreements are covered; estimates both sides missed stay invisible; the M1 gold is unchecked. 3 of the notes flag that the page showed a different estimate than the one meant (excerpt matching was tightened afterwards; ids and verdicts unchanged). |
| 6. Clean holdout | 25 never-annotated papers, code and predictions frozen and pushed before 3 new blind annotators ran (protocol, prompt and incident notes in `data/m1/independent/README.md`, `docs/blind-annotator-prompt.md`). | Out-of-sample F1 0.823 [0.753, 0.876]; pooled over 55 unseen papers 0.785 [0.707, 0.849]; the post-round-1 fixes changed no holdout prediction (A14). | The annotators are LLMs; independence is by instruction, not sandbox. |
| 8. Real-weights checks | PDF parser tested on real (generated) PDFs with PyMuPDF (B13). Stale dense index fixed. | The PDF path now has behaviour under test. | BERT tagger, NLI verifier, dense embeddings: not run, they need model downloads (see the list of what needs a human). |
| 9. Recall outside cardiometabolic | The holdout shows no established gap (A14). The 61 misses were read and sorted (independent README). Four general, verified fixes were made: `posterior interval` as an interval label, `HRadjusted =`-style qualifiers on HR/OR/RR, and guards against `Compared to their baseline ... (MD ...)` and `mean difference (SD)`. Each was checked on all 166 papers (4 false positives removed, 2 estimates gained, a first version that dropped a true positive from the frozen test gold was caught by the diff and narrowed). | The notation gaps are real; tuned F1 on the holdout 0.839 vs 0.823 clean. | **Not done**: the larger patterns (a long filler between metric and value, `OR per ... increase`, the metric named after the numbers, continuations without a metric word, bare lists) - they are riskier, and there is no unseen set left to measure them on. A fix tuned on the same papers is not evidence. |
