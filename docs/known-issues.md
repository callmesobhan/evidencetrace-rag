# Known issues and limitations

Everything below was found by the author, by five blind annotator agents, by a clean-room reproducer, or by a
red-team reviewer, and is stated here instead of being left for a reader to discover. Items are grouped by what they
threaten: the *evidence* (can the numbers be trusted), the *system* (what it cannot do), the *bugs* that were found and
how they were handled, and the *reproduction* (can you get the same numbers). Section E lists each red-team finding
with its status.

Throughout, "agent" means an LLM instance with its own context. **No human has verified any annotation, review or
number in this repository.** The reviewer, the annotators and the reproducer were agents too.

## A. Threats to the evidence

| # | Issue | Consequence | Status |
|---|---|---|---|
| A1 | The M1 gold standard (111 papers) was produced by a single LLM that is also the developer of the extractor; the review sheets showed it the system's own confidence and attribution. | Every M1 figure is "agreement between the system and one reviewer", not accuracy. Judgements of what counts as an estimate drifted with the extractor's scope. | Mitigated, not solved (A2). A human annotator is the most valuable missing piece. |
| A2 | The independent check (`data/m1/independent/`) is also LLM agents: five annotators, 36 papers, one annotator per paper except the 6-paper overlap with the developer. | Independence of *context*, not human ground truth. Shared model blind spots are possible. Intervals are wide. | Open. |
| A3 | Gold is pooled from the system's own output plus a near-miss audit. Dev precision 1.000 is by construction (0 rejected). | Precision is flattering; recall is an upper bound (estimates without a statistical cue are invisible). | Documented. |
| A4 | **The M1 test recall (0.950) did not generalise.** On 30 fresh papers annotated blind, the frozen system reaches recall 0.653 (F1 0.742): 0.874 / F1 0.902 on cardiometabolic papers, **0.365 / F1 0.477 on other domains**. | The headline M1 test F1 (0.957) describes cardiometabolic papers phrased the way the regexes were fitted to. Do not quote it as general accuracy. | Open. Fixes made afterwards raise the fresh F1 to 0.865, but they were made on those same papers: **not held-out**. |
| A5 | Agreement papers: independent vs developer F1 is 0.648 (0.718 if `IRR` and `RR` are one metric). One paper (PMC12810801, 35 odds ratios written `COR/p = 6.30/0.01`) accounts for most of the difference. | Both the system and the developer's gold missed a notation the developer had never seen. | Not extracted (deliberately: one paper). Guidelines v1.1 rule such estimates in scope. |
| A6 | Post-hoc changes after the test split was scored (`rarity_unit = "papers"`, `%-` ranges, scientific-notation p-values), and post-review changes after the independent annotation and the review. | Post-hoc / post-review columns are not held-out. | Labelled everywhere; `FROZEN.json` lists every changed file. |
| A7 | One test query label was wrong (1 of 43); only answered unanswerable queries were audited. | The label error rate is unknown. | Corrected via `label_corrections.json`; corrected frozen figure is 2 / 42. |
| A8 | **The corpus is not "111 randomized trials".** About a quarter (28 papers by a title screen: 15 dev, 13 test) are meta-analyses, cohort / cross-sectional / registry studies, protocols or a cost-effectiveness analysis; they supply 208 of 842 gold findings. `article_type` is `research-article` for all 111. | Wording corrected everywhere. No metric is split by design. One esaxerenone meta-analysis is 37 of 310 own test findings and the source of all 3 test false answers. | Wording fixed; design screening open. |
| A9 | Small samples: 48 test papers, ~43 answerable and ~43 unanswerable queries per split. | A `[0, 0]` bootstrap interval on zero events is an artefact; exact upper bounds are 19.1% for 3 of 43 and 8.4% for 0 of 42. | Reported with exact bounds. |
| A10 | **The false-answer headline is weaker than it looks.** The 14 *absent* queries cannot fail (their outcome word has document frequency 0, which the rarity gate always refuses). Only the 29 *cross* queries test anything: 3 / 29 = 10.3% (exact upper 27.4%). Cross queries exclude drug+outcome co-occurring in one sentence, i.e. the hard negatives. The 3 failures are one drug from one paper, and one is a label error. | The 7.0% overstates the evidence for wrong-drug protection. | Reworded; hard negatives open (B1). |
| A11 | Several metrics cannot fail by construction: provenance pass rate (parser re-finds its own number), value+CI identical to value-only (sheets pre-filled with the interval), span attribution (short gold quote inside the predicted sentence), p/n accuracy (copied from predictions), dev precision, population token-F1 (`None == None` counted as agreement). | They are consistency checks, not accuracy. | Relabelled in the report; population F1 now excludes empty pairs. A blind annotator filling CI / p / n is open. |
| A12 | The same clinical trials sit on both sides of the split (EMPACT-MI: PMC11955319 dev, PMC11115458 test; DAPA-HF: PMC8247863 dev, PMC10234442 / PMC7664959 / PMC9508991 test). | A split by paper id is not a split by trial; test is not fully independent of dev. | Documented. |
| A13 | The held-out "freeze" is a convention: hashes prove files are unchanged since the record was written, not *when* they were frozen relative to the test annotation, and one party ran the whole procedure. | The freeze is auditable for consistency, not for timing. | Stated in `FROZEN.json` (`limits_of_this_record`). |

## B. What the system cannot do (yet)

| # | Issue | Evidence |
|---|---|---|
| B1 | **Retrieval cannot bind roles.** Coverage and the rare-term gate are token presence. "Drug Zeta did not change stroke risk, whereas placebo increased myocardial infarction (HR 1.40)" answers a question about Drug Zeta and MI with the placebo arm's HR. | Reproduced; recorded as a strict `xfail` test (`tests/test_known_limits.py`). The README claim of wrong-drug protection is limited accordingly. |
| B2 | **Conflict detection is dormant on real text.** The rule field tagger fills any field for ~10% of findings, and conflicts need intervention and outcome on both sides. Also: ratio metrics of different kinds (HR vs OR) are compared on sign alone, `Interval.level` is ignored, and findings without an interval have confidence 0.45 < the 0.6 threshold so they are filtered before conflict detection. | 0 conflicts over 171 real-paper queries; tested on 5 synthetic papers only. |
| B3 | Lexical relevance gate refuses paraphrases. | 86% of hand-written paraphrases refused (35% of all answerable queries). The price of few false answers. |
| B4 | Unnamed estimates ("increased haemoglobin by 7.3 g/L (95% CI 6.2, 8.5)"), regression coefficients, rates, win ratios, tables and figures are out of scope. | About 5-15% of CI-bearing estimate sentences use no metric name. |
| B5 | The BERT tagger, NLI verifier, dense/hybrid retrieval and the PDF parser have **never been run against real model weights or real PDFs** (the LlamaIndex index is tested with a mock embedding). The persisted dense index is never invalidated when a paper is re-ingested. | Treat as unverified code. |
| B6 | Attribution (own vs cited) is a lexical heuristic. | 22% of findings labelled "cited" were really own (the safe direction); 1 of 139 "own" labels on fresh papers and 3 of 310 on the M1 test split were another study's result. |
| B7 | Estimates in unusual notation (`COR/p = 6.30/0.01`) or with a reversed printed interval are not recognised. | Strict `xfail` test. |
| B8 | A heart rate written `HR 72 (95% CI 70-74)` with no unit or context word is read as a hazard ratio (units, "heart rate" / "beats" context and "RR interval" are guarded). | Strict `xfail` test. |
| B9 | Covariate-balance SMDs are still extracted as effects when nothing in the sentence says "balance". | 8 of the 13 test false positives. |
| B10 | Non-English text: decimal commas are rejected rather than parsed. | 2 Portuguese passages in the corpus. |
| B11 | `Answer.confidence` is a transparent heuristic, not a calibrated probability. | `extractor._confidence`, `pipeline._answer_confidence`. |
| B12 | The downloader drops a whole 20-paper batch if one paper contains an `<!ENTITY` declaration; dependencies have lower bounds only and there is no lockfile. | Minor. |

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
