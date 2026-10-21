# Second adjudicator: instructions

## Round 2 (done 2026-10-21): re-judge 14 items under the adopted scope rules

Done: both judges re-judged the 14 items. The result is in [rules_round/result/rules_round.md](../data/m1/independent/adjudication/rules_round/result/rules_round.md) and in §2.4.3 of the report. The instructions below are kept as they were sent.

The first round is finished (69 items; kappa 0.43). The 12 disagreements came from two scope rules, which are now written down
as **guidelines v1.2** (the end of [annotation-guidelines.md](annotation-guidelines.md)). Round 2 asks you, and the repository owner,
to judge the 14 items on the two papers under those rules.

1. Read the v1.2 addendum, which is also shown on the page.
2. Open <https://callmesobhan.github.io/evidencetrace-rag/adjudication-rules.html>. Judge all 14 items: **y** (in scope under v1.2), **n**, or **u**.
   Notes are useful wherever you applied a rule.
3. Judge afresh. Do not copy your round-1 verdicts, and do not open the repository's `data/m1/independent/adjudication/` folder, which holds them.
4. Press **Download decisions (.jsonl)**. The file is `adjudication_decisions_rules.jsonl`. Send it to the repository owner.

About 20 minutes. Your progress saves in your browser, as before.

**No web page? Use the text file instead.** `python -I scripts/adjudication_form.py make --who second --out form.txt` writes the same 14 items
(rules, text, estimate) as a plain-text form with an `ANSWER` line under each item; the same command with `--who owner` writes the repository
owner's form. The judge types yes, no or unsure after the colon, optionally a `REASON` and a one-line `NOTE`, saves and sends the file back.
`python -I scripts/adjudication_form.py parse --who second --form filled.txt --out decisions_second.jsonl` checks it strictly (all 14 answered,
readable answers, the right judge's form) and writes the file the page would have exported. The two forms are separate so neither judge sees the
other's answers. The filled forms are kept next to the decisions in `data/m1/independent/adjudication/rules_round/`.

---

## Round 1 (finished): the 69 holdout items

One person (the repository owner) has judged the 158 places where the system and the blind annotators disagreed. A **second, independent**
person judging a subset gives an agreement figure, which says how much the verdicts depend on who is judging. This page is for that second person.

**Task:** 69 items, about an hour. Open <https://callmesobhan.github.io/evidencetrace-rag/adjudication-second.html>.

## The one question

For each item the page shows a sentence from an open-access paper (with the neighbouring sentences) and one highlighted estimate. Answer:
**is the highlighted number a genuine, in-scope effect estimate?** Read the
[annotation guidelines](annotation-guidelines.md) first, including the v1.1 addendum at the end. In short, it is in scope if it is a
**between-group (or between-time-point/exposure-level) point estimate** named as one of: hazard ratio, odds ratio, risk ratio, rate ratio,
mean difference, standardized mean difference (Cohen's d / Hedges' g only if named as such), risk difference. It is **not** in scope if it is:

- a planned or hypothetical value (power calculation, non-inferiority margin);
- a baseline-balance statistic;
- a change *within* one arm, or the "main effect of time";
- a rate, proportion or mean; a regression coefficient or correlation; an unnamed difference or bare "effect size".

Cited estimates (another study's result, quoted) **are** in scope. The number being in the paper is not enough, and who found it (the system or
the annotator) is irrelevant: judge the estimate itself. If you have to open the full paper to decide, do (each item links to it).

## How to use the page

- Keys: **y** = yes, in scope; **n** = no; **u** = unsure (use sparingly); **j** / **k** = next / previous. Buttons work too.
- For a "no", pick a reason from the menu if one fits. A short note is optional but useful where you were torn.
- Progress is saved in your browser (same browser, same link). You can stop and continue later. Nothing is sent anywhere until you press
  **Download decisions (.jsonl)**; send that file (`adjudication_decisions_second.jsonl`) to the repository owner.

## Rules that keep this a genuine second opinion

1. **Judge on your own.** Do not open `data/m1/independent/adjudication/` in the repository (it holds the first adjudicator's verdicts and notes) and do not
   discuss items with the first adjudicator until you have sent your file. (The repository is public, so this is a matter of honesty, not access control.)
2. **A person, not an AI.** If you used any AI assistance for any item, say so in the note on that item, or say so when you send the file.
3. **Say who you are, as far as you are willing:** your field or training (for example clinical epidemiology, biostatistics, medicine) and whether you
   may be named in the repository. Neither is required; the repository will record what you allow.

## What happens next

`scripts/adjudication_agreement.py --first data/m1/independent/adjudication/decisions.jsonl --second <your file> --out OUT` reports raw agreement,
Cohen's kappa, the confusion table, every item you and the first adjudicator disagree on (with both notes), and the frozen system's F1 on these
papers under each adjudicator's verdicts. As a rough convention, kappa above 0.8 is very strong agreement, 0.6-0.8 substantial, 0.4-0.6 moderate, below
0.4 weak; with 69 items the interval around kappa is wide (roughly plus or minus 0.1-0.15). Disagreements are **not** overwritten: both sets of
verdicts stay in the repository, and the headline accuracy is reported as a range if they differ. Where the two of you split on a *rule* (for example
whether an unnamed difference counts), that is evidence the guideline is ambiguous, not that one of you is wrong.
