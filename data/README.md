# Data

`samples/` is **entirely synthetic**: fictional drugs ("Zeta", "Omega"), fictional trials, fictional numbers. Each
paper carries a banner line saying so. Do not cite these as evidence of anything. `m1/` (below) is the only real data.

The five papers are built to contain specific traps:

| Paper | Trap it tests |
|---|---|
| `paper_a` | same result in Abstract and Results (dedupe); effect on *stroke* mentioned only next to a figure; *dizziness* described only qualitatively |
| `paper_b` | introduction quotes another study's HR (`cited`, must not be attributed to this paper); its own HR contradicts `paper_a` in direction |
| `paper_c` | non-significant result whose CI is disjoint from `paper_a`'s (magnitude) |
| `paper_d` | consistent with `paper_a`, but overlaps the null-crossing `paper_c` (significance) |
| `paper_e` | a different drug; `MI` abbreviation vs "myocardial infarction"; odds-ratio metric |

`samples/gold/` has `gold_findings.jsonl` (quotes, not offsets) and `gold_queries.jsonl` (expected
status, gold finding ids, gold conflicts). Real corpora go in `data/raw/` (git-ignored).

## Real data (M1)

`data/m1/` holds annotations, gold, predictions and scores for 111 CC BY open-access papers from PubMed Central
(cardiometabolic, 2019-2026; the query asked for randomized trials, but roughly a quarter are not) plus 55 further
papers used only for the independent blind annotation. The papers are **downloaded, not committed**:
`make fetch-pinned` restores exactly the pinned set and verifies each file's SHA-256. The data files quote sentences from
166 CC BY articles, credited in `data/m1/ATTRIBUTION.md`. See `data/m1/README.md`, `docs/m1-report.md` and
`docs/known-issues.md`.
