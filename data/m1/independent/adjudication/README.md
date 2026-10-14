# Adjudication of the system-vs-annotator disagreements

`decisions.jsonl` is the file exported by the review page ([docs/adjudication.html](../../../../docs/adjudication.html)) on 2026-10-14:
161 items (158 estimates + 3 study-design questions), every one decided, none left "unsure". Each line has the item id, a yes/no verdict
("is this a genuine in-scope effect estimate?"), a reason code for the "no" answers, and a free-text note.

> **Who judged:** the repository owner, who states that the verdicts and notes are their own work (the repository cannot verify authorship
> independently). Many notes record checks of the full paper that the review page does not show ("Checked source: Table 2 footnote",
> "Checked methods"). Their domain qualifications are not recorded, and there is a single adjudicator, so there is no inter-rater statistic
> for these verdicts. This is the only human judgement in the repository, and it covers the disagreements only: the M1 gold and the
> estimates both sides agreed on have no human check.

`apply_adjudication.py` turns the verdicts into corrected precision / recall / F1 (`make adjudication` regenerates and diffs these folders).

## What the 158 estimate verdicts say

| | in scope | not in scope | |
|---|---|---|---|
| annotator-only (129): the system missed it | **107** genuine misses | 22 annotator over-inclusion (12 unnamed differences / effect sizes, 4 regression slopes, 4 other, 2 within-arm) | annotators over-included 17% |
| system-only (29): the annotator did not record it | **17** real estimates the annotators missed | 12 genuine false positives (11 within-arm changes or "main effects of time", 1 a ratio of days lost labelled HR) | 59% of the "false positives" were right |
| study design (3) | PMC6837161: a real randomized trial as well as a Mendelian-randomization analysis | PMC7155116: observational cohort analysis nested in an RCT; PMC7395780: two-sample Mendelian randomization (PubMed's RCT tag is misleading) | `design.jsonl` still holds the classifier's labels |

## Corrected accuracy (value + CI match, 95% bootstrap CI over papers)

| system | as scored (annotator = truth) | adjudicated |
|---|---|---|
| frozen pre-fix system, **55 unseen papers pooled** | F1 0.785 [0.708, 0.849] (P 0.909, R 0.691) | **F1 0.837 [0.786, 0.884]** (P 0.962, R 0.740) |
| ...round 1 only (30 papers) | 0.742 [0.609, 0.865] | 0.834 [0.750, 0.909] |
| ...round 2 only (25 papers, clean holdout) | 0.823 [0.753, 0.876] | 0.839 [0.770, 0.892] |
| current code, both rounds (tuned on these papers) | 0.852 [0.806, 0.895] | 0.881 [0.841, 0.917] |

- **The two rounds agree once the disagreements are adjudicated** (0.834 vs 0.839), where as scored they differed (0.742 vs 0.823): much of the
  round-1/round-2 gap was annotator scope noise, not a property of the papers.
- **This only corrects the disagreements.** Matched estimates are assumed right, and an estimate that *both* the system and the annotators
  missed is invisible, so recall is still an upper bound.
- The notes also confirm specific system faults: the sign loss (`-3.35` shown as `+3.35`), omitted credible/posterior intervals, "main effect of time"
  and "compared to baseline" read as between-group estimates, and a ratio of days lost read as a hazard ratio.
