### `test` split - 48 papers, 360 gold findings, 355 predicted

| metric | value (95% cluster-bootstrap CI over papers) |
|---|---|
| value+CI precision | 0.963 [0.904, 0.997] |
| value+CI recall | 0.950 [0.899, 0.993] |
| value+CI F1 | 0.957 [0.916, 0.988] |
| value-only recall (ignores CI) | 0.950 [0.899, 0.993] |
| value-only precision (ignores CI) | 0.963 [0.904, 0.997] |
| **own-labelled results that are really cited ('leak')** | 0.010 [0.000, 0.023] |
| precision of 'own' labels | 0.952 [0.885, 0.989] |
| p-value accuracy (matched) | 0.991 |
| n accuracy (matched) | 1.000 |
| provenance verification pass rate | 0.997 |
| span attribution accuracy (matched) | 0.997 |
| field token-F1 on 29 annotated matched pairs (int / cmp / out / pop) | 0.17 / 0.07 / 0.06 / 0.97 |

Near-miss audit (sentences that look statistical but yielded no finding):

```
{
 "near_miss_sentences": 250,
 "geometric_mean_ratio": 3,
 "incidence_rate": 2,
 "needs_manual_look_(audited)": 39,
 "no_effect_estimate": 128,
 "regression_coefficient": 7,
 "relative_risk_reduction": 9,
 "unnamed_estimate_with_ci": 62
}
```

### `test` split - abstention on 86 queries (29 annotated-wording, 14 paraphrase, 29 cross, 14 absent)

| metric | value (95% bootstrap CI over queries) |
|---|---|
| **false-answer rate** (answered an unanswerable query), n=43 | 0.070 [0.000, 0.163] |
| - cross (real drug x another paper's outcome) | 0.103 [0.000, 0.241] |
| - absent (real drug x outcome nowhere in corpus) | 0.000 [0.000, 0.000] |
| **over-abstention rate** (refused an answerable query), n=43 | 0.349 [0.209, 0.488] |
| - annotated wording | 0.103 [0.000, 0.241] |
| - hand-written paraphrase | 0.857 [0.643, 1.000] |
| answerable queries whose target finding was returned (hit rate) | 0.651 [0.512, 0.791] |
| AURC (lower is better) | 0.314 |
| conflicts reported / answers carrying an 'unassessed pairs' caveat | 0 / 2 |
