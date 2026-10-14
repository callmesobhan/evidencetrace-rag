# Draft scope rules for the two disputed papers (status: DRAFT, not adopted)

**Why this exists.** The two adjudicators agree on 55 of the 69 holdout items. The 14 items on PMC12703296 and PMC12117457 are where they
split, because they read two scope rules differently. This memo sets out the choices, what each choice changes, and what is recommended.
Nothing here is adopted until the repository owner approves it. The re-judgement page `adjudication-rules.html` (in this folder, deliberately
not on the published site) is built from the **recommended** choices; if other choices are picked, the page is rebuilt from the matching text.

## What the existing verdicts say

- **Owner (first adjudicator):** on PMC12117457 counts the OR per 0.1 unit of NEE (`9d339eb3b3`) and the OR per 100 units of MAP:NEE (`4e3fae7d42`) as in scope,
  but counts the MD per 0.1 unit of NEE (`92bb0f03b7`) as out, with the note "continuous covariate slope per unit (age, weight, MAP or vasopressor
  dose)". NEE is the vasopressor dose, the paper's exposure. The same exposure on the same unit is therefore in scope or out depending only on
  the scale label. **That is an inconsistency in the first set of verdicts, not a principled distinction.**
- **Second adjudicator:** counts all six per-unit items on PMC12117457 as in scope, and all eight altitude contrasts on PMC12703296 as out.

## Rule 1: per-unit estimates from regression models (6 items on PMC12117457)

| Option | Per-unit estimates counted as in scope | Items that change vs the recommendation |
|---|---|---|
| **A2, recommended** | Only for the primary exposure of the paper (NEE, MAP:NEE). Covariate slopes (age, weight, MAP) are out, whatever the label (MD, OR, HR). | (reference) |
| A1, strict | None: every per-unit regression estimate is out (the v1 text, "regression coefficients / slopes", read literally). | `9d339eb3b3` and `4e3fae7d42` (the NEE ORs) go out; the owner and second adjudicator both counted them in. |
| A3, permissive | All per-unit estimates, whatever the variable or label (the second adjudicator's reading). | `79c82ed19d` (age), `e5f0149661` (weight), `4b57ba3bba` (MAP) come in; the owner counted them out. |

Why A2: it keeps the guideline's own exposure language ("compares ... exposure levels"), matches the owner's verdicts on every item except
`92bb0f03b7`, and removes the scale-label inconsistency. The cost is that "primary exposure" needs a judgement per paper, which the judges make from the text.

## Rule 2: a contrast between two conditions described as "mean change" (8 items on PMC12703296)

Within a crossover trial, high versus low altitude is a contrast between two exposure levels in the same people. The paper's table calls the
result a "mean change"; the text says "higher by" or "lower by", often with the word "versus".

| Option | Reading | Items that change vs the recommendation |
|---|---|---|
| **B2, recommended** | In scope as a mean difference when the text states the contrast between the two named conditions. | (reference) |
| B1, strict naming | Out unless the text uses "mean difference" or "difference" as the metric name. "Mean change" does not name a difference. | All 8 altitude items go out (the second adjudicator's reading). |

Why B2: the guideline's scope is "compares two groups, arms, exposure levels or time points", and this is a comparison of exposure levels. The
unnamed-difference exclusion is about a difference with no named metric (`unnamed_difference`). These items name both the comparison (high versus
low) and the metric the paper uses ("mean change"), so B2 reads them in, while B1 treats "mean change" as not a named difference. The cost of
B2 is that it depends on reading "versus" and "higher by" as comparisons, which the judges check against the text.

## What the page's 14 items would read as under the recommended rules (a reading, not a verdict)

| id | paper | metric and value | owner | second | under A2 / B2 |
|---|---|---|---|---|---|
| 9d339eb3b3 | PMC12117457 | OR 1.09 per 0.1 unit NEE | yes | yes | in (primary exposure) |
| 4e3fae7d42 | PMC12117457 | OR 0.99 per 100 units MAP:NEE | yes | yes | in (exposure index) |
| 92bb0f03b7 | PMC12117457 | MD -2.1 per 0.1 unit NEE | no | yes | in (flips from the owner's verdict) |
| 79c82ed19d | PMC12117457 | MD -0.54 per year of age | no | yes | out (covariate) |
| e5f0149661 | PMC12117457 | MD 0.19 per kg weight | no | yes | out (covariate) |
| 4b57ba3bba | PMC12117457 | MD 0.49 per mm Hg MAP | no | yes | out (covariate) |
| 8 altitude items | PMC12703296 | MD, high vs low altitude | yes | no | in (contrast between named conditions) |

The judges make the actual verdicts from the page, under the rules as written in its intro. This table is only what the rules imply, so that
the owner can check the rules do what they are meant to do before anyone judges.

## What this does and does not settle

- It measures whether two people apply the **same** rules the same way. It does not show which rule is right.
- Under the recommended rules, the holdout F1 range will move; the 0.839 to 0.848 range (rules as the two adjudicators applied them) is no longer
  the right figure once the items are re-judged. Report whichever figure the agreed rules produce, and say which rules.
