# M1 report: the first real-data baseline

**One paragraph.** We fetched 111 CC BY open-access papers from PubMed Central (cardiometabolic, 2019-2026; the
query asked for randomized trials, but PubMed labels only **67 of the 111 as trials** (42 of 63 dev, 25 of 48 test): 16 are evidence syntheses, 8 observational, 3 protocols, 1 an economic evaluation, and 16 are plain journal articles with no trial label), fixed a dev/test split by PMCID hash *before* looking at anything, audited
the system's output on dev (355 predictions → ~20 distinct bug classes), froze the code, then audited the held-out
test split and scored it once. On the held-out split the extractor reaches **F1 0.957** (P 0.963, R 0.950) against
a single LLM annotator's gold, **labelled 3 of 310 "own" results with another study's number** (1.0%), and
**answered 3 of 43 unanswerable questions** (7.0%; the exact 95% upper bound is 19%) while **refusing 35% of
answerable ones** (86% of hand-written paraphrases). The rule-based field tagger fills any field for only ~10% of
findings, so **conflict detection never fired once on real papers**.

Two later checks changed how those numbers should be read. **Five blind LLM annotators** labelled 30 papers the
system had never seen: the frozen system scored **F1 0.742** there (0.902 on cardiometabolic papers, **0.477 on
other domains**), so the 0.957 describes a narrow slice, not the system in general (§2.4). A **red-team review**
found that several headline metrics cannot fail by construction and that the "Trace" guarantee was
overclaimed; those are corrected below and in [known-issues.md](known-issues.md).

> **Read [What the numbers do and don't mean](#5-what-the-numbers-do-and-dont-mean) before quoting any figure.**
> The M1 gold and the blind annotations were made by LLMs, and the M1 gold has no human check. The repository owner later adjudicated the
> system-vs-annotator disagreements (§2.4.2): a single human adjudicator, covering the disagreements only.

## 1. What was built

| artifact | where | size |
|---|---|---|
| Corpus acquisition (licence-filtered, XML-safe, deterministic split, SHA-256-pinned manifest) | `src/evidencetrace/ingest/pmc.py`, `scripts/fetch_pmc.py`, `data/m1/corpus_manifest.jsonl` | 111 CC BY papers (63 dev / 48 test) |
| Annotation sheets: every prediction + every "statistical-looking sentence with no prediction" | `data/m1/annotation/*_candidates.jsonl`, `*_nearmiss.jsonl` | dev 464 / 331, test 355 / 250 |
| Reviewer decisions (rejections, corrections, field annotations, verified misses) | `data/m1/annotation/*_review.json` | |
| Gold findings (quote-anchored; validated against the parsed paper) | `data/m1/gold/*_gold_findings.jsonl` | dev 482, test 360 |
| Frozen query sets (annotated-wording, paraphrase, cross, absent) | `data/m1/queries/` | dev 85, test 86 |
| Baseline snapshot of the first extractor | `data/m1/annotation/v1/` | 355 dev predictions |
| Freeze record + the two exact frozen sources | `data/m1/FROZEN.json`, `frozen_snapshot/`, `frozen_snapshot_fresh/` | all hashes recomputed by `scripts/verify_freeze.py` |
| Scored results | `data/m1/results/` (frozen source), `data/m1/results_postreview/` (current code) | |
| Independent blind annotation + scores | `data/m1/independent/` | 36 papers, 5 annotators |
| Study design of every paper (PubMed publication types + title phrases) | `data/m1/design.jsonl`, `results_by_design/` | 166 papers |
| Hard-negative queries and their scores | `data/m1/queries/*_hardneg_queries.jsonl`, `results_hardneg/` | dev 17, test 18 |

**Protocol.** (1) Split by `sha1(PMCID)` before any code ran. (2) Run the extractor; audit dev predictions
(precision) and dev near-misses (recall); fix bugs; repeat. (3) Freeze (`FROZEN.json` records a hash of
`src/` + config; the snapshot reproduces it). (4) Generate test sheets with the frozen code, audit them the same
way, **do not change extractor code**. (5) Write test paraphrases *before* running the system on them. (6) Score
once. Everything after (5) that touched `src/` is listed and labelled **post-hoc** or **post-review** in `FROZEN.json`.

**Gold construction is pooled, not independent.** A gold finding is a system prediction the reviewer accepted
(or corrected), plus true estimates found by the near-miss audit. The sheets the reviewer read were pre-filled with
the system's own metric, value, interval, p-value, attribution and confidence (anchoring). See §5.

## 2. Results

Brackets are 95% cluster-bootstrap intervals (resampling **papers** for extraction, **queries** for abstention).
"Frozen" columns come from `data/m1/frozen_snapshot/` and are the held-out numbers; "current" columns come from the
present code with `configs/posthoc.toml` and are **not held-out** (several fixes were motivated by test failures).

### 2.1 Extraction

| | dev, first extractor | dev, final (frozen) | **test, frozen (held-out)** | test, current code |
|---|---|---|---|---|
| value+CI precision | 0.777 [0.685, 0.857] | 1.000 ¶ | **0.963** [0.904, 0.997] | 0.986 [0.966, 0.997] ‖ |
| value+CI recall | 0.573 [0.469, 0.669] | 0.963 [0.937, 0.984] | **0.950** [0.899, 0.993] | 0.950 |
| value+CI F1 | 0.659 [0.562, 0.746] | 0.981 [0.967, 0.992] | **0.957** [0.916, 0.988] | 0.967 [0.937, 0.991] ‖ |
| "own" label that is really cited (leak) | n/a | 0 / 437 | **3 / 310 = 1.0%** [0.0, 2.3]; exact upper bound 2.8% | same |
| labelled "cited" but really the paper's own | n/a | 6 / 27 | 10 / 45 (22%) | same |
| findings with *any* field tagged by rules | n/a | 11% | 10% | same |
| field token-F1: intervention / comparator / outcome | n/a | 0.06 / 0.09 / 0.04 (n=35) | 0.17 / 0.07 / 0.06 (n=29) | same |

Consistency checks, **not accuracy** (they cannot fail the way an extractor fails):

| | test, frozen | why it cannot fail |
|---|---|---|
| provenance pass rate 0.997 | numbers are extracted by regex from a sentence and then re-found in the same sentence. It measures parser self-agreement, not correctness. | |
| "value+CI" tp/fp/fn = "value-only" tp/fp/fn (342 / 13 / 18 in both) | the annotation sheets arrive pre-filled with the system's interval, p-value and attribution, so the CI condition never discriminates. | |
| p-value 0.991 and n 1.000 correct on matched | gold p and n were copied from predictions and corrected only where noticed. | |
| span attribution 0.997 | the gold quote is a short substring (median 28 characters) of the predicted sentence. | |
| population token-F1 0.97 (frozen `.md` only) | `token_f1(None, None) = 1.0`: two empty fields counted as agreement. Excluded in current code (population is 0.50 on test). | |

‖ The covariate-balance filter (post-hoc): the 8 balance-diagnostic SMDs (`SMD = 0.312` for comorbidity prevalence) are all from one
paper (PMC13278687) and no true estimate in any of the 166 papers is lost. It was written after seeing them in the test review, so the
improvement is **not held-out**; the held-out figure stays 0.963 / 0.957. On dev, the current extractor also finds 6 estimates the frozen
dev gold lacks (3 between-group Cohen's d, 3 spaced-minus mean differences); on reading they are correct, so the current dev
precision of 0.987 *understates* it. The pinned dev gold is deliberately not edited.

¶ Dev precision of 1.000 is **entirely by construction**: `dev_gold_meta.json` records 0 rejected predictions, because
every false positive found on dev was removed by changing the code, not by marking it wrong.

The dev→test drop (F1 0.981 → 0.957) is a rough measure of how much of the dev score was fitting. §2.4 shows that the
test score itself overstates generalisation outside this corpus.

#### 2.1.1 By study design

Because only 67 of the 111 papers are confirmed trials, extraction was scored separately (`scripts/stratify_m1.py`, current code, brackets = 95%
bootstrap over papers; the strata are small, so read the intervals):

| split | group | papers | gold | precision | recall | F1 | "own" that are cited |
|---|---|---|---|---|---|---|---|
| dev | confirmed trials | 42 | 329 | 0.981 | 0.951 | **0.966** [0.944, 0.985] | 0 / 301 |
| dev | not confirmed as trials | 21 | 153 | 1.000 | 0.974 | **0.987** [0.961, 1.000] | 0 / 140 |
| test | confirmed trials | 25 | 184 | 0.977 | 0.935 | **0.956** [0.909, 0.989] | 1 / 167 |
| test | not confirmed as trials | 23 | 176 | 0.994 | 0.966 | **0.980** [0.934, 1.000] | 2 / 135 |

Extraction accuracy does **not** depend on whether the paper is a trial: the non-trials (mostly meta-analyses, which report in a regular
style) score slightly higher and the intervals overlap broadly. The design problem therefore changes how the corpus must be *described*, not
the extraction numbers. Design labels come from PubMed's publication types and explicit title phrases; 3 papers (2 test, 1 fresh; one of the test papers is genuinely ambiguous) are flagged where the two disagree for a human to read (`design.jsonl`, field `disagree`).

### 2.2 Abstention (queries built from the field-annotated findings)

Queries are *answerable* (a gold finding exists: annotated wording or hand-written paraphrase) or *unanswerable*:
**cross** = a drug from paper A with an outcome from paper B where no sentence mentions both, **absent** = a real drug
with an outcome that appears in no paper (glaucoma, hip fracture, ...).

| | dev, first retriever | dev, final (frozen) | **test, frozen** | test, current code |
|---|---|---|---|---|
| **false answers**, all unanswerable | 9 / 41 = 22.0% | 0 / 41 | **3 / 43 = 7.0%** (bootstrap upper 16.3%; **exact 95% upper bound 19.1%**) | 0 / 42 (exact upper 8.4%) |
| ...of which **cross** queries | | | **3 / 29 = 10.3%** (exact upper 27.4%) | 0 / 28 |
| ...of which **absent** queries | | | 0 / 14 (cannot fail, see below) | 0 / 14 |
| over-abstention on answerable queries | 43.2% | 36.4% [22.7, 50.0] | **34.9%** [20.9, 48.8] | 32.6% [18.6, 46.5] |
| ...annotated wording | 22.2% | 18.5% | 10.3% | 6.9% |
| ...hand-written paraphrase | 76.5% | 64.7% | **85.7%** [64.3, 100] | 85.7% |
| answerable queries whose target finding was returned | 47.7% | 61.4% | 65.1% | 67.4% |

How to read the false-answer row:

- **The "absent" queries cannot fail.** Their outcome word is by construction in no paper, so it has document
  frequency 0, which the rare-term gate treats as rare and unmatched, so they always abstain. Only the cross queries
  test anything; the honest test figure is **3 / 29 = 10.3%**, with a wide interval.
- **The cross queries exclude the hard negatives**, so §2.2.1 adds them.
- **The 3 false answers are one drug from one paper**: an esaxerenone meta-analysis contributes 37 of the 310 own test
  findings. They are not three independent failures.
- **One of the three is a label error** (the paper writes the drug "ESAX" and does report SBP; the system was right).
  Corrected, frozen test is 2 / 42 = 4.8% (exact upper bound 16.2%). The current-code column excludes it.
- A `[0, 0]` bootstrap interval on zero events is an artefact of the bootstrap; the exact 95% upper bound for 0 / 42 is 8.4%.

#### 2.2.1 Hard negatives: asking about the reference arm

`cross` and `absent` queries use words that never co-occur, so they cannot test whether the system understands *which arm* a number belongs to.
Hard negatives can: for every field-annotated finding that compares a specific intervention with a reference arm ("Drug X vs placebo on SBP"),
ask "What is the effect of **placebo** on SBP?". Every word of the query is in the paper's sentence, but the sentence reports the drug's effect
*relative to* placebo, not an effect of placebo, so the right answer is to abstain. (A labelling judgement; a reader could argue the contrast
also answers it. A query is dropped if the gold itself reports the control as an intervention on that outcome.) Real annotations contain no
sentence with two different interventions, so within-sentence role swaps cannot be mined; they are covered by a small synthetic set below.

| system | dev (n = 17) | test (n = 18) |
|---|---|---|
| frozen source | **15 / 17 answered** (88%) | **17 / 18 answered** (94%) |
| current code (clause-scoped, role-aware retrieval) | **0 / 17** (exact 95% CI 0-19.5%) | **2 / 18** (exact 95% CI 1.4-34.7%) |

The frozen system presented a drug-versus-placebo contrast as "the effect of placebo". The fix (a clause splitter, reference-arm tracking, and
requiring the most distinctive intervention word to appear as a *subject*) was developed against these same queries, so the "current" row is
**tuned on them, not held-out**; it is evidence that the mechanism works, not an estimate for new data. It cost nothing on answerable
queries (over-abstention and hit rate identical on both splits; false answers still 0 on the ordinary unanswerable queries). The two test
queries still answered ask about "the control group" in a meta-analysis where "control" has several senses. On a labelled synthetic corpus
(`data/samples_hardneg`, 7 role-swap / placebo-as-intervention queries, written knowing the fix: a regression test, not evidence) the frozen
source's false-answer rate is 1.000 and the current code's 0.000, with no over-abstention. With the old default configuration the current code
also gives 2 of 43 test false answers (frozen: 3 of 43).

**AURC.** The frozen figures (dev 0.436 → 0.328, test 0.314) were computed with a definition that scores every
*correct abstention as an error* and ranks abstentions in the curve, so they mostly track the abstention rate and
contradict the definition in [evaluation.md](evaluation.md). Recomputed over answered queries only (the reviewer's figure
from `results/test.json`): 0.0098 (3 errors among 31 answered). Current code reports the corrected definition:
**dev 0.0195, test 0.000** (no answered test query was wrong). With so few errors the metric has almost no resolving
power here; it is reported for completeness. The synthetic-corpus eval now reports 0.000 for its perfect system
(it reported 0.224 under the old definition).

### 2.3 Conflicts

**0 conflicts reported across 171 queries on both splits.** Not because the corpus has none, but because conflict
detection needs intervention + outcome on both findings and the rule tagger supplies them for ~10% of findings. Two
test answers carried the "N pairs could not be checked" caveat; the design intent (never fail silently) held, but the
feature is dormant on real text, and it has only ever been tested on five synthetic papers.

### 2.4 Independent (blind) annotation

Five separate LLM agents, each with its own context, annotated 36 papers (30 never seen + 6 from the test split) from
the guidelines alone, without seeing system output or the developer's gold. Full protocol, files and caveats:
[data/m1/independent/README.md](../data/m1/independent/README.md). The system's predictions were generated by the frozen
source and hashed **before** the annotation existed.

| held-out: frozen system vs independent annotation, 30 fresh papers (196 estimates) | precision | recall | F1 |
|---|---|---|---|
| all | 0.859 [0.721, 0.962] | 0.653 [0.507, 0.805] | **0.742** [0.609, 0.865] |
| 15 cardiometabolic papers | 0.933 | 0.874 | **0.902** [0.827, 0.962] |
| 15 other-domain papers | 0.689 | 0.365 | **0.477** [0.284, 0.692] |
| *after the fixes this found (tuned on these papers, NOT held-out)* | 0.963 | 0.786 | *0.865* [0.799, 0.930] |

- **Recall did not generalise.** M1 test recall was 0.950; round 1 gave 0.874 on fresh cardiometabolic papers and 0.365 on other
  domains (round 2, §2.4.1, gives 0.702 and 0.783). The M1 near-miss audit could only find estimates near a statistical cue the developer already knew.
- **Annotator agreement** on the 6 overlap papers (independent vs developer): F1 0.648, or 0.718 if "incidence rate
  ratio" and "rate ratio" are one metric; attribution kappa 1.0. One paper (35 odds ratios written `COR/p = 6.30/0.01`)
  dominates the difference.
- **Attribution** held up: 1 of 139 "own" labels was another study's result; kappa 0.89 against the independent
  own/cited judgement.
- **A sign-loss bug in the frozen extractor** (`difference of – 3.35 g/m2` → +3.35) was found this way. Diffing the
  frozen against the fixed extractor over all 111 M1 papers gives zero sign-only differences and no change at all on the
  test split, so no published M1 number is affected.

#### 2.4.1 A clean holdout, and the pooled estimate

Round 1's post-fix figure (0.865) is tuned on the papers it is measured on. A second blind round on the **25 fresh papers nobody had
seen**, with the code and predictions committed and hashed *before* the annotators started
([protocol](../data/m1/independent/README.md)), gives the out-of-sample number:

| system as frozen, unseen papers | papers | precision | recall | F1 |
|---|---|---|---|---|
| round 2 (clean holdout) | 25 | 0.952 | 0.724 | **0.823** [0.753, 0.876] |
| round 2, current code *(4 notation fixes made after reading these papers: TUNED)* | 25 | 0.982 | 0.733 | 0.839 [0.773, 0.895] |
| round 1, pre-fix system (held-out) | 30 | 0.859 | 0.653 | 0.742 [0.609, 0.865] |
| **both rounds pooled, pre-fix system** | **55** | 0.909 | 0.691 | **0.785** [0.707, 0.849] |

- The fixes made after round 1 **changed no prediction on the 25 holdout papers** (identical 168 predictions before and after), so the
  pre-fix and post-review systems have the same out-of-sample score here; the 0.742 → 0.865 round-1 gain is a tuning effect.
- The round-1 "other domains" gap (recall 0.365) is **not reproduced** (0.783 on 10 papers); with such samples it is neither confirmed
  nor refuted.
- Of the misses, the sampled ones are genuine notation gaps (long fillers, `OR per ... increase`, the metric named after the numbers,
  `HRadjusted =`, `posterior interval`, continuations without a metric word) plus scope disagreements and matching quirks;
  see the round-2 section of the independent README.

#### 2.4.2 Adjudicating the disagreements

All 158 estimate disagreements (129 annotator-only, 29 system-only) and the 3 study-design disagreements were judged on the review page
([verdicts, notes and method](../data/m1/independent/adjudication/README.md)). The owner judged all 158; a **second adjudicator judged the 69 clean-holdout
items** (§2.4.3 below). The owner states the verdicts are their own. The second adjudicator is a medical researcher who asked not to be named and did not use AI on any item (as reported by the owner; not verifiable from the repository).

- Of the 129 items the system "missed", **107 are genuine misses and 22 (17%) are annotator over-inclusion** (12 unnamed differences or effect sizes,
  4 regression slopes, 4 other, 2 within-arm). Of the 29 "false positives", **17 are real estimates the annotators did not record** and 12 are real
  false positives (11 within-arm changes or "main effects of time", 1 a ratio of days lost read as a hazard ratio).

| frozen pre-fix system | as scored | adjudicated |
|---|---|---|
| 55 unseen papers pooled | F1 0.785 [0.708, 0.849] (P 0.909, R 0.691) | **F1 0.837 [0.786, 0.884]** (P 0.962, R 0.740) |
| round 1 (30 papers) / round 2 (25 papers, clean holdout) | 0.742 / 0.823 | 0.834 / 0.839 |

- **The two rounds agree after adjudication** (0.834 vs 0.839): most of the round-1/round-2 gap was annotator scope noise.
- This corrects only the disagreements. Matched estimates are assumed right and an estimate both sides missed is invisible, so recall remains an
  upper bound; and the M1 test-split figures (0.957) rest on the developer's own gold, which this does not touch.

#### 2.4.3 A second adjudicator (the 69 clean-holdout items)

A second person judged the 69 holdout disagreements independently ([instructions](second-adjudication.md)); the two files are in
[data/m1/independent/adjudication/](../data/m1/independent/adjudication/README.md), and `make adjudication` regenerates the agreement.

| | |
|---|---|
| items both judged | 69 (all decided; 0 "unsure") |
| raw agreement | 0.826 (57 of 69) |
| Cohen's kappa | 0.43; paper-clustered 95% interval [-0.08, 1.00] over 16 papers (too wide to be informative at this size) |
| where they disagree | 12 items on **two papers**; on the other 55 items the adjudicators agree every time |

The 12 disagreements are two **scope-rule** questions, not readings of the papers (the owner's NEE verdicts also need a consistent rule, see item 2):

1. **"Mean change" between conditions** (PMC12703296, altitude crossover, 8 items). The first adjudicator counts a named "mean change" contrast as a
   mean difference; the second does not, because no mean-difference metric is named. The guideline's unnamed-difference exclusion favours the second reading.
2. **Per-unit regression estimates labelled "MD" or "OR"** (PMC12117457, 6 items). The first counts the age, weight and MAP slopes out (covariates) and the
   NEE odds ratios in (the paper's exposure), but counts the NEE mean difference out as a "covariate slope". The same NEE exposure on the same unit is
   in or out depending on the scale label: an inconsistency in the first set of verdicts. The second counts all six in because the paper labels them
   per-unit mean differences or odds ratios. The v1 guideline lists regression slopes as out of scope, which supports the first on the covariates.

Effect on the holdout F1 (both sets of verdicts on the same 69 items, the 25 papers, adjudicated):

| verdicts used | precision | recall | F1 |
|---|---|---|---|
| as scored (annotator = truth) | 0.952 | 0.724 | 0.823 [0.753, 0.876] |
| first adjudicator | 0.964 | 0.743 | 0.839 [0.770, 0.892] |
| second adjudicator | 0.964 | 0.757 | **0.848** [0.791, 0.897] |

The second adjudicator's reading was the more favourable one for the system (recall +0.014), entirely through the 12 rule items. Before the rules were decided, the honest figure for this subset was the range 0.839 to 0.848.

**Round 2 (2026-10-21): the 14 items re-judged under the adopted rules.** The owner and the second adjudicator each re-judged the same 14 items under guidelines v1.2. The forms and reasons are in [rules_round](../data/m1/independent/adjudication/rules_round/README.md); the figures are in [result/rules_round.md](../data/m1/independent/adjudication/rules_round/result/rules_round.md).

- **Agreement: 14 of 14** (kappa 1.0; no "unsure"). Under the rules 11 items are in scope and 3 are out. The per-year age, per-kg weight and per-mm Hg MAP mean differences are covariate slopes (Rule 1: out). The NEE odds ratios, the MAP:NEE ratio and the per-unit NEE mean difference are the paper's exposure (Rule 1: in). The eight altitude contrasts are between-condition differences (Rule 2: in).
- **Holdout F1 under the adopted rules: 0.837 [0.769, 0.889]** on the 25 clean-holdout papers. It is the same for both judges, because their verdicts are identical. Before the rules it was 0.839 (owner) and 0.848 (second). The 0.839 in §2.4.2 is the owner's original verdicts; 0.837 is the figure under the adopted rules.
- **The rules moved the two judges unequally.** The owner's verdict changes on one item (the NEE mean difference, now in). The second judge's changes on eleven (eight altitude contrasts, now in; three covariate slopes, now out). The owner approved the rules on 2026-10-14, and they were written from the same 12 disagreements. So the 14-of-14 agreement is measured in-sample: it shows the rules remove the split on these items, but it is not an independent agreement figure. The independent figure is still kappa 0.43 on the 69 items (round 1).
- **Record.** The owner's form has a note on every item. The second judge's form has verdicts only, so their reasons are not on record beyond the verdicts. Both forms state no AI assistance (as stated; not verifiable from the repository).

## 3. What the audit changed in the system

Each item was found by reading real predictions, then covered by a regression test (82 → 285 tests including the
post-review ones).

- **Parser.** Regex section detection put 302 of 1,177 findings in "Introduction" and labelled 666 of them `cited`
  (most wrongly, since real papers rarely use the five heading names it knew). Now sections come from JATS structure;
  tables/figures/LaTeX are skipped. 60 of the first 114 papers were *reviews* (PMC has no publication-type index);
  acquisition now goes through PubMed's `randomized controlled trial[pt]`, which still admits studies that merely
  mention a trial (§5).
- **Numbers.** `[0.1, 1.6]`, unlabelled `(0.69–1.10)`, `[CI]` labels, `RR0.33`, unit tokens (`ml/kg/min`), list
  continuation (`0.80 (…) for MI, 0.71 (…) for stroke, …`), `aRR/AOR/WMD/AMD/SHR/RMD`-style names, bare filler
  phrases. Sanity checks drop (never "repair") an estimate outside its own CI, a ratio with a unit, a decimal-comma
  number, a power-calculation sentence, flattened table text. `n` is no longer taken from event counts.
- **Attribution.** Citation markers split sentences incorrectly (`KFRT.[11] Chlorthalidone…`); in Discussion/Conclusion
  a number is now "own" only if the sentence says so (`we/our/this study`). This removed every cited-as-own error on dev
  and shrank it to 3 on test.
- **Verification.** Spaced minus signs, `%-` ranges, scientific-notation p-values; tolerance is relative, so
  `p = 2.01e-5` cannot verify `2.02e-5`. **Post-review:** a positional check (`estimate_reproduced`) re-derives the
  estimate from the span and requires metric, value, interval and p-value to agree, because "the number occurs
  somewhere in the sentence" let a swapped interval, a flipped p-operator, or the CI's lower bound read as the
  estimate all verify; the document hash is recomputed from the text rather than compared as two stored strings.
- **Retrieval (post-review follow-up).** Findings now carry the *clause* that holds the estimate (split at `whereas`, `, while`, `in contrast`, and at `;` only between two estimates), the field tagger runs on that clause rather than the whole sentence (before, `Zeta did not change stroke, whereas placebo increased MI (HR 1.40)` gave the placebo finding the intervention "Drug Zeta" and the outcome "stroke"), text after `vs / compared with / than` and generic control words (`placebo`, `usual care`, `control group`) count as reference-arm text, and the most distinctive word of the asked-about intervention must appear as a subject. A `;` that merely separates statistics was tried as a boundary and cost two answerable dev queries before it was made conditional.
- **Retrieval.** A **rare-term gate** (a finding lacking a query term that is rare in the corpus is not relevant,
  however good its weighted coverage) cut dev false answers from 22% to 0. Within-paper **abbreviation expansion**
  (`GLS ↔ global longitudinal strain`, Schwartz–Hearst) and hyphen-compound tokens (`semaglutide-treated`) cut
  annotated-wording over-abstention from 48% to 18.5%.
- **Rejected on evidence.** Indexing the paper title (to recover the intervention a Results sentence omits) made an LDL
  question answerable with the paper's myocardial-infarction result. Reverted; `Finding.context` keeps the title for display only.
- **From the independent annotation and the review** (all post-hoc, none held-out): credible intervals, LSMD, Cohen's d,
  number-inside-filler, the sign-after-filler bug, DOI and within-arm guards, Lancet middle-dot decimals,
  scientific-notation p-values (`3.1e-4`, `10^-5`, `P<10-4` were read as 3.1, 1.2, 10), heart-rate / RR-interval
  guards, unique finding ids (three pairs collided on the frozen code), `p<0.05` counted as significant, differing
  units not compared as a conflict, AURC redefined.

## 4. Failure gallery (held-out test)

**13 false positives / 355 predictions** (frozen). The current extractor filters the 8 balance-diagnostic SMDs, leaving 5 / 355 (post-hoc, §2.1).
- 8 × `SMD` that are propensity-score *covariate-balance diagnostics* (`SMD = 0.312` for comorbidity prevalence), not effects
- 2 × "mean difference –1.8% vs –0.8%": per-arm changes, not a contrast
- 1 × a prespecified noninferiority margin ("odds ratio was 1.2")
- 1 × "difference in mean 24 h natriuresis was 63 (95% CI…)" parsed as the estimate **24**. This one passes provenance:
  24 is in the sentence.
- 1 × a restatement with the opposite sign convention

**18 missed true estimates / 360** (all of a supported metric)
- 6 × `RMD` (raw mean difference), absent from the metric registry
- 6 × "odds ratios for a medication refill by the last day of available medication (established at enrollment) were 0.98 (…) in arm 1, …": parenthetical inside the filler
- 5 × hazard ratios behind a `%`, a long filler, or a "per standard deviation" list
- 1 × the real natriuresis estimate (the other half of the false positive above)

**3 attribution leaks (cited, labelled own)**: a DECLARE-TIMI58 HR in a sentence that also says "we observed"; a
published regression equation's RR beside "the current study"; a registry HR in a review-style section. Rule: the
own-cue is a lexical proxy for authorship and a sentence can carry both.

**False answers (3).**
1. `esaxerenone × (an empagliflozin outcome)` ×2: **the rarity gate counted findings, and one esaxerenone meta-analysis
   contributes 37 of the 310 own findings (11.9%)**, so the drug looked common (>10%) although it appears in one paper. Fix: count papers
   (`rarity_unit = "papers"`, post-hoc).
2. `esaxerenone × systolic blood pressure`: **my label was wrong.** The paper writes the drug "ESAX" and does report
   SBP; the new abbreviation aliasing found it, my "provably absent" check ignored aliases. The system was right.
   1 / 43 queries mislabelled is itself a data point about query-construction quality; only unanswerable-but-answered
   queries were audited for label errors, so the true rate is unknown.

**Over-abstention.** 12 of 14 paraphrases refused (`cutting salt intake`, `resistance exercise`, `repeat admissions`,
`protect kidney function`: synonyms the lexical gate cannot bridge). Of 29 annotated-wording queries 3 refused, mostly
because the Results sentence never names the intervention ("the adjusted HR for all-cause mortality was 0.73"). Both
are the cost of preferring a refusal to a wrong answer, and both need the same two things: concept normalisation and
paper-level intervention inheritance via a working field tagger.

## 5. What the numbers do and don't mean

1. **Single annotator who is also the developer, an LLM, no human check of the gold** (the adjudication in §2.4.2 covers only the independent-annotation disagreements). Treat every M1 number as "agreement between
   the system and one reviewer", not accuracy. The reviewer found and fixed bugs in the code it was auditing, so its
   judgments of what counts as an "effect estimate" drifted with the extractor's scope. The review sheets showed the
   system's own confidence and attribution (anchoring).
2. **The independent check is also LLM agents** (§2.4). It adds independence of context, not human ground truth, and
   shared model blind spots are possible.
3. **Pooled gold inflates precision.** Dev precision 1.000 is by construction (nothing was rejected); test precision
   0.963 is the better figure and is still anchored.
4. **Recall is an upper bound** and was shown to be optimistic: 0.950 on the M1 test split, 0.653 on fresh papers.
5. **Dev is fitted; test is only partly clean.** The post-hoc columns used test failures to motivate fixes: do not
   quote them as held-out.
6. **The corpus is not "111 randomized trials".** The query asked for them, but `article_type` is `research-article` for all 111
   and design was never screened. PubMed's publication types and title phrases (`data/m1/design.jsonl`) show 67 confirmed trials
   (42 dev, 25 test) and 44 others: 16 evidence syntheses, 8 observational, 3 protocols, 1 economic evaluation, 16 untyped journal
   articles. One esaxerenone meta-analysis alone is 37 of 310 own test findings and the source of all three frozen test false
   answers. Extraction accuracy is the same for both groups (§2.1.1); the abstention queries have not been split by design.
7. **The same trials sit on both sides of the split** (EMPACT-MI in dev PMC11955319 and test PMC11115458; DAPA-HF in dev
   PMC8247863 and test PMC10234442, PMC7664959, PMC9508991): splitting by paper id is not splitting by trial.
8. **Scope.** Roughly 5% (dev) to 15% (test) of CI-bearing estimate sentences use no metric name at all; plus regression
   coefficients, rates, relative-risk reductions, win ratios. Out of scope by design, not counted as misses.
9. **Corpus.** Cardiometabolic, 2019-2026, selected by a query requiring effect-size words in the abstract; it favours
   the reporting style the regexes expect, and §2.4 measures the cost (0.365 recall on other domains).
10. **Small queries.** ~43 answerable and ~43 unanswerable per split; intervals are wide; queries are synthetic and the
    paraphrases were written by the same author. See §2.2 for what the false-answer rate does and does not test.
11. **Retrieval binds roles only lexically.** The frozen system answered "the effect of placebo on X" with a drug-vs-placebo contrast in
    88-94% of hard-negative queries (§2.2.1). Clause scoping and reference-arm tracking fix the cases below, but they are
    string heuristics: they do not parse grammar, "but"/"although" are not split points (elliptical subjects), a control word used
    in another sense ("active control", "blood pressure control") still leaks, and a sentence comparing subgroups within the placebo arm
    is ambiguous. The fix is tuned on the hard negatives it was measured on.
12. **Not measured at all:** conflict detection on real papers, the BERT tagger, NLI verification, dense retrieval, PDF
    parsing, tables.

## 6. What the evidence says to do next

1. **M2 is justified, with a sharper goal.** Fields are the bottleneck for conflicts (0 detected), for
   intervention-less sentences (4/29 refused), and for field-level F1 (<= 0.17). Add "inherit the paper's primary
   intervention from the title/abstract when the sentence has none". Fields are now tagged from the estimate's own clause.
2. **Make paper-level rarity the default** once re-validated on fresh papers; keep the rare-term gate. Hard negatives and
   exact intervals are now reported (§2.2.1); what is still missing is a hard-negative set that was *not* used to develop the fix: annotate the
   25 never-annotated fresh papers and build one.
3. **M3 targets the 65-86% paraphrase refusal**: concept normalisation (MeSH/UMLS) and a cross-encoder relevance score
   *behind* the rare-term gate, so recall can rise without reopening the wrong-drug hole.
4. **Get a human second annotator.** The LLM-agent check in §2.4 is done; a human on ~20 papers (no predictions shown),
   with kappa on effect/not-effect and own/cited, is still the most valuable missing piece.
5. **Registry gaps** worth the effort: unnamed "difference of X (95% CI)", `RMD`, "treatment ratio", `COR/p`-style
   notation, a filter for covariate-balance SMDs, and non-cardiometabolic phrasing (0.365 recall).
6. **A human adjudication** of the 89 disagreements between the system and the blind annotators, and of the 3 design disagreements.

## 7. Reproduce

```bash
pip install -e ".[dev]"                 # Python >= 3.11
make fetch-pinned                       # exactly the 111 + 55 pinned papers (~22 MB, CC BY), SHA-256 verified
make verify-freeze                      # every hash in data/m1/FROZEN.json recomputed from the committed files
make m1-frozen                          # held-out numbers, from the frozen source; diffs against data/m1/results
make m1                                 # current code + configs/posthoc.toml; diffs against data/m1/results_postreview
make independent                        # held-out + post-review predictions (byte-compared) and the independent scores
make design by-design hardneg           # study design (offline), extraction by design, hard-negative scores; `make design-live` asks PubMed today
make eval-hardneg                       # the synthetic role-swap set
```

`make reproduce` runs all of it. Nothing overwrites a tracked file: outputs go to `reports/` (git-ignored) and are
diffed. `scripts/run_m1.py --frozen` refuses to run unless the frozen source is the one actually imported, which
catches the `PYTHONPATH` + `python -I` mistake (isolated mode ignores `PYTHONPATH` and would silently run the current
code). Result files round floats to 12 digits, so they are identical across Python versions (3.12 made float `sum()`
compensated; unrounded they differed in the 16th digit of one value on 3.11).

The one-time construction of the annotation files from a fresh download is also scripted
(`scripts/make_candidates.py`, `build_gold.py`, `make_queries.py`), but the review decisions in between are
human-in-the-loop (here: LLM) judgements stored in `data/m1/annotation/*_review.json`, so they are inputs, not outputs.
`make_queries.py` reads the hand-written paraphrases from `data/m1/queries/` (override with `--paraphrases`), not from
`--out`, so a fresh output directory no longer silently drops them.

`make fetch-new` discovers *new* papers; PubMed's ranking and PMC's holdings drift, so that path is not reproducible and
the pinned manifests are what the committed numbers refer to. If PMC changes a paper's XML the pinned SHA-256 no
longer matches. The fetch then checks the canonical text (`data/m1/canonical_pins.jsonl`): if only PMC's bookkeeping changed, the paper is accepted and logged in `data/m1/drift_log.md`; if the text changed, the fetch reports drift and exits non-zero. Papers are not redistributed;
[ATTRIBUTION.md](../data/m1/ATTRIBUTION.md) credits all 166 articles whose sentences the data files quote.
