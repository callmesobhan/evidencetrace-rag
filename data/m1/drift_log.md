# Drift log: PMC records that changed after pinning

Pins are checked against what NCBI serves today (`scripts/fetch_pmc.py --from-manifest`). Two kinds of change are distinguished:

- **metadata** (accepted): PMC's own bookkeeping changed and the canonical text the results depend on is identical. The canonical text is
  pinned in `canonical_pins.jsonl` and checked on every fetch.
- **content** (drift): the article's text changed. The file is not written and the reproduction stops.

| date (UTC) | PMCID | kind | what changed | canonical text | effect on results |
|---|---|---|---|---|---|
| 2026-10-19 | PMC11170842 (fresh set, holdout 2) | metadata | `pub-history/event[@event-type="pmc-last-change"]` date: 2024-06-14 to 2026-10-18 (PMC re-processed the record) | identical (sha256 a245c03e…) | none: `make reproduce` regenerates the holdout predictions, scores and adjudication byte-for-byte from the current record |

Found by the scheduled reproduction run of 2026-10-19, which failed at `fetch-pinned` (the pin then compared the whole raw record). The
fetch logic was changed to the two-level check; the run was then repeated in full.
