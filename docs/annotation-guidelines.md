# Annotation guidelines (v1)

These guidelines let a second annotator label papers **without seeing any system output** and without talking
to the system's developer. They encode the scope decisions that were made implicitly during M1.

## The task

For each paper, list every **effect estimate** the text reports: a number that compares two groups, arms,
exposure levels or time points, reported as a *point estimate* (optionally with a confidence interval and p-value).
Read the paper paragraph by paragraph. Do not skim; estimates hide in subgroup sentences, lists, abstracts and
discussion paragraphs that quote other studies.

## In scope: seven metrics

| metric | what it is | how the text may write it |
|---|---|---|
| `HR` | hazard ratio | hazard ratio, HR, aHR, adjusted/subdistribution HR, sub-HR, SHR |
| `OR` | odds ratio | odds ratio, OR, aOR, uOR, AOR |
| `RR` | risk ratio / relative risk | risk ratio, relative risk, RR, aRR |
| `IRR` | rate ratio | incidence rate ratio, rate ratio, IRR |
| `MD` | mean difference between groups/time points | mean difference, MD, WMD (weighted), RMD (raw), AMD (adjusted), between-group / treatment difference, "difference in means" |
| `SMD` | standardized mean difference | standardized mean difference, SMD, Cohen's d / Hedges' g **only if it is a between-group effect size** |
| `RD` | risk difference | risk difference, RD, aRD, absolute risk reduction/difference (a *difference*, not a percentage of baseline) |

A value counts with or without a CI or p-value. Every item of a list is its own estimate:
"HR 0.80 (0.66-0.97) for MI, 0.71 (0.66-0.77) for stroke" is **two** records.

## NOT effect estimates (do not record as findings)

Record these under `out_of_scope` only when they carry a CI (see below); otherwise ignore them.

- **Baseline/balance statistics**: an SMD used to show covariate balance after matching or weighting
  ("SMD = 0.31 for hypertension prevalence"). Not an effect.
- **Planned or hypothetical values**: sample-size assumptions ("80% power to detect HR 0.80"), noninferiority or
  equivalence margins ("prespecified margin OR 1.2"), minimal clinically important differences, thresholds
  ("a difference of 1 point or more").
- **Within-arm change** called a "difference" or reported with its own CI: "hemoglobin rose 7.3 g/L (95% CI...)
  in the drug arm". A contrast *between* arms is in scope; a change *within* one arm is not.
- **Rates, proportions, prevalence, means** with a CI (event rate 4.1/100 PY, 61% (95% CI 45-73), mean 133.7 mmHg).
- **Regression coefficients / slopes / correlations / R^2 / AUC / kappa / I^2 / NNT / relative-risk-reduction
  percentages / win ratios / ratios of geometric means / median differences.** Not in the seven-metric scope.
- **Heterogeneity and interaction p-values** are never the p-value *of an estimate*.

## Out-of-scope estimates we still want counted

For any sentence that reports an estimate-like quantity **with a confidence interval** that you excluded, add one
record to the out-of-scope file with a `category`:

`unnamed_difference` (a difference/change with a CI but no named metric), `rate_or_proportion`,
`regression_coefficient`, `rrr`, `win_ratio_or_other_ratio`, `balance_diagnostic`, `planned_value`,
`within_arm_change`, `other`.

## Fields for each in-scope estimate

| field | rule |
|---|---|
| `doc_id` | the paper id you were given |
| `quote` | an **exact substring** of the paper text, as short as possible, covering the metric name (if adjacent), the value and its CI. Copy-paste; do not retype. It must occur in the text. |
| `metric` | one of the seven above |
| `value` | the point estimate as a number; negatives with a leading `-`. Write `0.60`, not "0.6 (approximately)" |
| `ci` | `[low, high]` exactly as printed, or `null` if no interval is printed. A printed interval that does not contain the point estimate (typo in the source) is still recorded as printed, and you set `ci_inconsistent: true`. |
| `p_value`, `p_operator` | the p-value reported **for that estimate** and its operator (`<`, `=`, `>`, `<=`, `>=`), else `null`. "p = 1.02 x 10^-6" is `1.02e-6`. Interaction/trend/heterogeneity p-values are not the estimate's p-value. |
| `attribution` | `own` if the paper reports it as its own result (including its own pooled meta-analysis and its own subgroup/sensitivity analyses); `cited` if the paper is quoting another study, trial, registry, guideline, or published equation (introduction background, discussion comparisons "in trial X, HR 0.81", a number carrying a citation to another work). If a pooled meta-analysis cites its included studies next to its own pooled estimate, the pooled estimate is `own`. When genuinely unsure, choose `own` and add `"uncertain": true`. |

Record each distinct estimate **once**. If the same estimate (same metric, value and CI) appears in the abstract and in
the results, record one record, preferring the Results occurrence.

## Output

Two JSONL files (one JSON object per line):

- `annotations.jsonl`: in-scope estimates with the fields above (+ optional `ci_inconsistent`, `uncertain`, `note`).
- `out_of_scope.jsonl`: `{"doc_id", "quote", "category"}`.

Validate before you finish: `python scripts/validate_annotations.py --inputs <dir> --annotations <file> [--out-of-scope <file>]`.
The validator checks that every quote occurs in the paper and every field has a legal value; it cannot check that you
found everything, so re-read each paper's Results and Abstract a second time for estimates you missed.

## Known judgement calls (document yours in `note` if you hit one)

- "Between-group differences of 3% (95% CI -4 to 9)" for cumulative incidence is a difference of proportions: record as `MD` if the
  text says "difference", `RD` only if it says risk difference / absolute risk reduction.
- A mean difference of an *age* or other baseline characteristic between subgroups, with a CI, is a statistic of the
  kind we count (`MD`); we do not try to separate treatment effects from descriptive contrasts.
- Percent-formatted estimates ("RR 0.76 (95% CI 0.32-1.80)") are the same as unformatted ones.
- Decimal-comma languages: record them normally (`0.38`) if you can read them reliably.

## v1.1 addendum (written AFTER the blind annotation of 36 papers)

The five independent annotators worked from v1 above. These rulings were added afterwards, from the cases they
flagged, so that a future annotator does not have to guess; none of them changes how the existing independent
annotation was scored, except where stated.

- **Reversed printed interval.** If the text prints a confidence interval with its bounds in descending order
  (`95% CI 8.5 to 6.2`), record `ci` as `[low, high]` in ascending order and say so in `note`. If the point estimate is
  outside the interval after sorting, also set `ci_inconsistent: true`.
- **Unnamed "effect size".** A bare "effect size 0.24" or "standardised effect 0.5" that the text does not call
  Cohen's d, Hedges' g or SMD is **not** an `SMD`. Record it under `out_of_scope` as `unnamed_difference` if it carries a CI,
  otherwise ignore it. (Several annotators recorded such quantities as in-scope and flagged them `uncertain`; they
  count as annotator-only items in the score files.)
- **Rate ratio naming.** Record the metric name the text uses: "incidence rate ratio" / "rate ratio" is `IRR`, "risk ratio" /
  "relative risk" is `RR`. The two are different estimands but papers use them loosely, so `scripts/score_blind.py
  --lenient-metrics` also reports a score that treats them as one metric; both variants are published.
- **Odds ratios without an interval** (`COR/p = 6.30/0.01`, "OR 2.1, p = 0.03") are in scope with `ci: null`. A
  paper that reports dozens in one table-like paragraph makes one record per estimate.

## v1.2 addendum (adopted after the holdout-2 re-judgement; approved by the repository owner)

Written after the second round of blind annotation, which the annotators did under v1 and v1.1. Two scope rules had been applied
differently by the two adjudicators on PMC12703296 and PMC12117457. These are the rules now, and they apply to any future
judgement. The first-round verdicts on those two papers were made under v1.1, so they are re-judged on `docs/adjudication-rules.html`
rather than changed in place. Full rationale: `data/m1/independent/adjudication/rules_round/RULES_DRAFT.md`.

- **Per-unit estimates from regression models.** An estimate given per one unit of a continuous variable is in scope only if that
  variable is the primary exposure the paper is about (for example the vasopressor dose in a study of kidney replacement therapy).
  Per-unit estimates for covariates the model adjusts for (for example age, weight or mean arterial pressure) are out of scope, whatever
  scale label the paper uses (MD, OR, HR). A categorised exposure compared with a reference level is in scope.
- **Contrasts between two named conditions.** A contrast between two named conditions or exposure levels reported in the same paper
  (for example high versus low altitude in a crossover trial) is in scope as a mean difference when the text states it as a difference
  between those conditions, including "higher by" or "lower by" wording, even if a table labels it "mean change". A change from baseline
  within one condition is out of scope.

