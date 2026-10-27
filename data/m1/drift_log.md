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

`make design` asks PubMed for every paper's publication types again and compares the result with the committed
`design.jsonl` (`scripts/check_design.py`). The results read only the committed classification (design, basis, disagree), and
PubMed keeps indexing records after publication, so the same two kinds of change are distinguished:

- **indexing** (accepted): publication types were added or removed, and every paper's classification is unchanged. Printed by the check.
- **classification** (drift): a paper's design, basis or disagreement flag changed, or a paper appeared or disappeared. The reproduction stops.

| date (UTC) | PMCID | kind | what changed | classification | effect on results |
|---|---|---|---|---|---|
| 2026-10-26 | PMC11593758 (PMID 39591427, dev split) | indexing | PubMed added the type "Research Support, Non-U.S. Gov't" | unchanged: trial, from PubMed, no disagreement | none: the committed `design.jsonl` is what the results read |

Found by the scheduled reproduction run of 2026-10-26, which failed at `design` (the check then compared the files byte for byte). Every
earlier step of that run was identical. The check was changed on 2026-10-27, applying the owner's rule of 2026-10-19 (above) to the
PubMed lookup: indexing changes are accepted and printed, classification changes stop the reproduction. The committed `design.jsonl` was
not edited; it remains the record of the lookup the results were computed from.

