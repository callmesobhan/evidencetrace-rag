# Re-judgement under the adopted scope rules (14 items, PMC12703296 and PMC12117457)

- `RULES_DRAFT.md`: the choices, what each changes, the recommendation the owner approved on 2026-10-14, and the adopted text.
- `intro.txt`: the text shown on the page (the adopted rules, v1.2).
- Page (public): https://callmesobhan.github.io/evidencetrace-rag/adjudication-rules.html (source: `docs/adjudication-rules.html`).
- Text-file route (no web page needed): `scripts/adjudication_form.py make|parse`, see `docs/second-adjudication.md`. The filled forms are kept here as
  `form_owner.txt` and `form_second.txt`.
- Status: done 2026-10-21. Filled forms: `form_owner.txt`, `form_second.txt`. Verdicts: `decisions_owner.jsonl`, `decisions_second.jsonl`
  (parsed by `scripts/adjudication_form.py parse`). Result: `result/rules_round.md` and `result/rules_round.json` (`make rules-round`).
