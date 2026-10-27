# Drift log: NCBI records that changed after pinning

## PMC article records

Pins are checked against what NCBI serves today (`scripts/fetch_pmc.py --from-manifest`). Two kinds of change are distinguished:

- **metadata** (accepted): PMC's own bookkeeping changed and the canonical text the results depend on is identical. The canonical text is
  pinned in `canonical_pins.jsonl` and checked on every fetch.
- **content** (drift): the article's text changed. The file is not written and the reproduction stops.

| date (UTC) | PMCID | kind | what changed | canonical text | effect on results |
|---|---|---|---|---|---|
| 2026-10-19 | PMC11170842 (fresh set, holdout 2) | metadata | `pub-history/event[@event-type="pmc-last-change"]` date: 2024-06-14 to 2026-10-18 (PMC re-processed the record) | identical (sha256 a245c03e…) | none: `make reproduce` regenerates the holdout predictions, scores and adjudication byte-for-byte from the current record |

Found by the scheduled reproduction run of 2026-10-19, which failed at `fetch-pinned` (the pin then compared the whole raw record). The
fetch logic was changed to the two-level check; the run was then repeated in full.

**Decision (2026-10-19, repository owner):** the two-level rule is adopted. A change to PMC's bookkeeping with identical canonical text is
accepted and logged; a change to the canonical text stops the reproduction. The raw-record pin stays in the manifests as the record of the
bytes first pinned.

## PubMed design lookup

PubMed keeps indexing records after publication (it adds and revises publication types), so what it says today is not what it said when
`design.jsonl` was committed. The reproduction therefore does not depend on it:

- **`make design`** (part of `make reproduce`) recomputes every classification from the committed record's own publication types and the
  manifests' titles, and checks each PMID against the paper's own metadata. No network; the same answer every week. If it fails, the
  committed record was edited inconsistently.
- **`make design-live`** (the weekly `drift-watch` workflow, Tuesdays) asks PubMed again and compares. It is a signal for a person, not a
  reproducibility test:
  - *indexing* (accepted, printed): publication types changed and every paper's classification is unchanged.
  - *classification* (the workflow turns red): a paper's design, basis or disagreement flag changed, or a paper appeared or disappeared.
    The committed results are unchanged. Decide, then record the decision here: either keep `design.jsonl` as the record of the lookup the
    results were computed from (log it and move on), or re-run `scripts/fetch_design.py`, `make by-design` and `make hardneg`, update the
    affected figures in the report, and commit the new record as a deliberate change.

| date (UTC) | PMCID | kind | what changed | classification | effect on results |
|---|---|---|---|---|---|
| 2026-10-26 | PMC11593758 (PMID 39591427, dev split) | indexing | PubMed added the type "Research Support, Non-U.S. Gov't" | unchanged: trial, from PubMed, no disagreement | none: the committed `design.jsonl` is what the results read |

Found by the scheduled reproduction run of 2026-10-26, which failed at `design` (it then compared the live lookup with the committed file
byte for byte, inside the reproduction). On 2026-10-27 the check was first made tolerant of indexing changes, and then the live lookup was
moved out of the reproduction into `drift-watch`, so that PubMed re-indexing cannot turn the reproduction red. The committed
`design.jsonl` was not edited.

## Papers committed (2026-10-27)

`data/raw/pmc/` (110) and `data/raw/fresh/` (54) now hold 164 of the 166 papers, under CC BY 4.0 (`data/raw/NOTICE.md`). The file
of PMC11170842 committed is the 2026-10-18 record: its raw `sha256` in `fresh_manifest.jsonl` is for the 2024-06-14 record, so the file
verifies through its canonical-text pin, as in the table above. The two not committed (PMC7814507, PMC12829467) are downloaded and
verified by `make fetch-pinned`; their details are in `data/raw/excluded.json`. The owner decided on 2026-10-27 to keep them out.

