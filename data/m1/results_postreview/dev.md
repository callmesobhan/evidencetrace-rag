### `dev` split - 63 papers, 482 gold findings, 468 predicted

| metric | value (95% cluster-bootstrap CI over papers) |
|---|---|
| value+CI precision | 0.987 [0.965, 1.000] |
| value+CI recall | 0.959 [0.932, 0.981] |
| value+CI F1 | 0.973 [0.956, 0.987] |
| value-only recall (ignores CI) | 0.959 [0.932, 0.981] |
| value-only precision (ignores CI) | 0.987 [0.965, 1.000] |
| **own-labelled results that are really cited ('leak')** | 0.000 [0.000, 0.000] |
| precision of 'own' labels | 0.986 [0.963, 1.000] |
| p-value accuracy (matched) | 1.000 |
| n accuracy (matched) | 1.000 |
| provenance verification pass rate | 1.000 |
| span attribution accuracy (matched) | 0.998 |
| field token-F1 on 35 annotated matched pairs (int / cmp / out / pop) | 0.03 / 0.03 / 0.04 / 0.33 |
| *baseline extractor before fixes*: P / R / F1 | 0.777 [0.685, 0.857] / 0.573 [0.469, 0.669] / 0.659 [0.562, 0.746] |

Near-miss audit (sentences that look statistical but yielded no finding):

```
{
 "near_miss_sentences": 331,
 "auc": 2,
 "geometric_mean_ratio": 2,
 "incidence_rate": 14,
 "median_difference": 2,
 "needs_manual_look_(audited)": 41,
 "no_effect_estimate": 198,
 "non_english": 2,
 "regression_coefficient": 29,
 "relative_risk_reduction": 12,
 "unnamed_estimate_with_ci": 28,
 "win_ratio": 1
}
```

### `dev` split - abstention on 85 queries (27 annotated-wording, 17 paraphrase, 27 cross, 14 absent)

| metric | value (95% bootstrap CI over queries) |
|---|---|
| **false-answer rate** (answered an unanswerable query), n=41 | 0.000 [0.000, 0.000] |
| - cross (real drug x another paper's outcome) | 0.000 [0.000, 0.000] |
| - absent (real drug x outcome nowhere in corpus) | 0.000 [0.000, 0.000] |
| **over-abstention rate** (refused an answerable query), n=44 | 0.364 [0.227, 0.500] |
| - annotated wording | 0.185 [0.037, 0.370] |
| - hand-written paraphrase | 0.647 [0.412, 0.882] |
| answerable queries whose target finding was returned (hit rate) | 0.614 [0.477, 0.750] |
| AURC (lower is better) | 0.020 |
| conflicts reported / answers carrying an 'unassessed pairs' caveat | 0 / 0 |
