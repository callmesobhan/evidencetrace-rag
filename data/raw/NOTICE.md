# Notice for the papers in `data/raw/`

## What is here

- `pmc/` (110 files) and `fresh/` (54 files): the full text of 164 open-access research articles from PubMed Central (PMC), one
  file per article (`PMCxxxxxxx.xml`). They are the corpus behind the M1 evaluation (see `data/m1/`).
- `excluded.json`: the two articles in the manifests that are **not** committed, with the licence text that excluded them.

## Licence

Every committed article is published under **Creative Commons Attribution 4.0 (CC BY 4.0)**, https://creativecommons.org/licenses/by/4.0/.
The licence is stated in each file's own `<permissions>` block. This notice does not apply the repository's MIT licence to these files:
the repository's `LICENSE` covers the code and the original annotations only.

How the licence was checked (2026-10-27): every one of the 166 articles in the manifests was read from its own XML. Across the 166 there
are 23 distinct opening wordings of the licence statement, all naming CC BY 4.0. None names NonCommercial, NoDerivatives or ShareAlike. The check then looked for
conflicting limits in the copyright lines, and found two articles (below) whose copyright line says "No commercial re-use" while their
licence statement grants commercial use. Those two are not committed. Two articles have no copyright line in their XML; their licence
statement is CC BY 4.0, and they are committed with the licence cited in `data/m1/ATTRIBUTION.md`.

This is a check of the publishers' own statements. It is not legal advice.

## Not committed (2)

| PMCID | where it would be | why |
|---|---|---|
| PMC7814507 | `pmc/` | BMJ: copyright line "Re-use permitted under CC BY. No commercial re-use."; licence statement "CC BY 4.0 ... for commercial use" |
| PMC12829467 | `fresh/` | the same BMJ wording |

The reproduction still needs them: `make fetch-pinned` downloads them from NCBI and checks them against the same pins. Whether to commit
them was the repository owner's decision. On 2026-10-27 the owner decided to keep them out. Their details are in `excluded.json`.

## Changes made to the files

Each file is the `<article>` element of PMC's JATS XML, re-serialised by Python's `xml.etree`: the XML declaration and the `DOCTYPE` are
removed and namespace prefixes are normalised. CC BY 4.0 asks for an indication of changes, and this is it. The text the analysis reads is
pinned for each article (`data/m1/canonical_pins.jsonl`); the raw bytes PMC served are pinned in the manifests (`sha256`).

One article is the record as PMC served it on 2026-10-18 (PMC11170842): PMC updated its `pmc-last-change` date from 2024-06-14, and the text
is unchanged. The manifest's raw `sha256` is for the 2024 record, so this file matches the canonical pin instead. See `data/m1/drift_log.md`.

## Attribution

`data/m1/ATTRIBUTION.md` gives, for every article, the authors, title, journal, year, DOI, copyright statement and licence, and links the
original on PMC.

## Verifying the files

`make fetch-pinned` checks each file already on disk against its pins without network access and downloads only the files that are missing
(the two not committed). `make design` checks the study-design record offline.

## Requests

If a rights holder objects to any file here, open an issue at https://github.com/callmesobhan/evidencetrace-rag/issues; the file will be
removed. The article remains available from its publisher and from PMC.
