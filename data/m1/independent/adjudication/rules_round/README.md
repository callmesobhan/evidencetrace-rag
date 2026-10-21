# Re-judgement under the adopted scope rules (14 items, PMC12703296 and PMC12117457)

- `RULES_DRAFT.md`: the choices, what each changes, the recommendation the owner approved on 2026-10-14, and the adopted text.
- `intro.txt`: the text shown on the page (the adopted rules, v1.2).
- Page (public): https://callmesobhan.github.io/evidencetrace-rag/adjudication-rules.html (source: `docs/adjudication-rules.html`).
- Text-file route (no web page needed): `scripts/adjudication_form.py make|parse`, see `docs/second-adjudication.md`. The filled forms are kept here as
  `form_owner.txt` and `form_second.txt`.
- Results go in `decisions_owner.jsonl` (the owner) and `decisions_second.jsonl`-style files from the second adjudicator, then
  `scripts/rules_round_result.py` computes agreement and the holdout F1 under the adopted rules.
