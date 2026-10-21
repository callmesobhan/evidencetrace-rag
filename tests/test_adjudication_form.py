import json
import re
from pathlib import Path

import pytest

from evidencetrace.evaluation.adjudication import load_decisions
from evidencetrace.evaluation.adjudication_form import (
    FormError,
    highlight,
    parse_form,
    records_jsonl,
    render_form,
)

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "adjudication-rules.html"
INTRO = "Rule 1, something.\n\nRule 2, something else."


def _items() -> list[dict]:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', PAGE.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def _fill(form: str, answers: dict[int, str], reasons: dict[int, str] | None = None, notes: dict[int, str] | None = None) -> str:
    """Type into the form the way a person would: after the colon of the n-th ANSWER / REASON / NOTE line."""
    out, n = [], 0
    for ln in form.split("\n"):
        key = ln.split(" ")[0].split(":")[0]
        if key == "ANSWER":
            n += 1
            ln += answers.get(n, "")
        elif key == "REASON":
            ln += (reasons or {}).get(n, "")
        elif key == "NOTE":
            ln += (notes or {}).get(n, "")
        elif ln.startswith("AI ASSISTANCE"):
            ln += "no"
        out.append(ln)
    return "\n".join(out)


def test_form_has_all_14_page_items_and_the_rules():
    items = _items()
    form = render_form(items, INTRO, "second")
    assert len(items) == 14 and form.count("===== ITEM ") == 14
    assert all(f"[id {i['id']}]" in form for i in items)
    assert "FORM-FOR: second" in form and "Rule 2, something else." in form


def test_owner_and_second_forms_differ_only_in_the_header_and_notice():
    items = _items()
    a, b = render_form(items, INTRO, "owner"), render_form(items, INTRO, "second")
    assert a != b
    assert a[a.index("===== ITEM 1 "):] == b[b.index("===== ITEM 1 "):]


def test_form_never_shows_anyones_earlier_verdicts():
    form = render_form(_items(), INTRO, "second").lower()
    assert "decision" not in form and "verdict is" not in form


def test_roundtrip_gives_the_pages_export_format_and_loads_in_the_pipeline(tmp_path):
    items = _items()
    form = _fill(render_form(items, INTRO, "owner"), {i: "yes" for i in range(1, 15)} | {2: "no", 5: "no", 7: "unsure"},
                 reasons={2: "within_arm", 5: "coef"}, notes={2: "within one arm"})
    records, meta = parse_form(form, items, "owner")
    assert len(records) == 14 and meta["ai_assistance"] == "no" and not meta["warnings"]
    assert records[1] == {"id": items[1]["id"], "kind": "estimate", "pmcid": items[1]["pmcid"], "decision": "no",
                          "reason": "within_arm", "note": "within one arm"}
    path = tmp_path / "d.jsonl"
    path.write_text(records_jsonl(records), encoding="utf-8")
    loaded = load_decisions(path)
    assert set(loaded) == {i["id"] for i in items}
    assert {r["decision"] for r in loaded.values()} == {"yes", "no", "unk"}


@pytest.mark.parametrize("typed,expected", [("yes", "yes"), ("YES", "yes"), (" y ", "yes"), ("Yes, in scope", "yes"), ("no", "no"),
                                            ("N", "no"), ("No - within arm", "no"), ("unsure", "unk"), ("u", "unk"), ("Unsure.", "unk")])
def test_answers_are_read_the_way_people_type_them(typed, expected):
    items = _items()
    records, _ = parse_form(_fill(render_form(items, INTRO, "owner"), {i: typed for i in range(1, 15)}), items, "owner")
    assert {r["decision"] for r in records} == {expected}


def test_windows_line_endings_bom_and_a_retyped_label_are_accepted():
    items = _items()
    form = _fill(render_form(items, INTRO, "owner"), {i: "yes" for i in range(1, 15)})
    form = "﻿" + form.replace("ANSWER (yes / no / unsure): yes", "ANSWER: yes", 1).replace("\n", "\r\n")
    records, _ = parse_form(form, items, "owner")
    assert len(records) == 14


def test_reason_spelling_and_a_reason_on_a_yes():
    items = _items()
    form = _fill(render_form(items, INTRO, "owner"), {i: "no" for i in range(1, 15)}, reasons={1: "Within-Arm", 2: "within arm"})
    records, _ = parse_form(form, items, "owner")
    assert records[0]["reason"] == records[1]["reason"] == "within_arm"
    form = _fill(render_form(items, INTRO, "owner"), {i: "yes" for i in range(1, 15)}, reasons={3: "coef"})
    records, meta = parse_form(form, items, "owner")
    assert records[2]["reason"] is None and any("reason is dropped" in w for w in meta["warnings"])


def test_an_unanswered_or_unreadable_item_is_refused_and_named():
    items = _items()
    form = _fill(render_form(items, INTRO, "owner"), {i: "yes" for i in range(1, 15) if i not in (4, 9)} | {9: "maybe"})
    with pytest.raises(FormError) as exc:
        parse_form(form, items, "owner")
    text = " ".join(exc.value.problems)
    assert "item 4" in text and "empty" in text and "item 9" in text and "'maybe'" in text


def test_bad_reason_code_is_refused():
    items = _items()
    form = _fill(render_form(items, INTRO, "owner"), {i: "no" for i in range(1, 15)}, reasons={6: "not relevant"})
    with pytest.raises(FormError, match="REASON 'not relevant'"):
        parse_form(form, items, "owner")


def test_the_other_judges_form_is_refused():
    items = _items()
    form = _fill(render_form(items, INTRO, "second"), {i: "yes" for i in range(1, 15)})
    with pytest.raises(FormError, match="is for second, not for owner"):
        parse_form(form, items, "owner")


def test_missing_duplicated_and_foreign_items_are_refused():
    items = _items()
    form = _fill(render_form(items, INTRO, "owner"), {i: "yes" for i in range(1, 15)})
    start = form.index("===== ITEM 3 ")
    end = form.index("===== ITEM 4 ")
    with pytest.raises(FormError, match=rf"item \[{items[2]['id']}\] is missing"):
        parse_form(form[:start] + form[end:], items, "owner")
    with pytest.raises(FormError, match="appears twice"):
        parse_form(form[:end] + form[start:end] + form[end:], items, "owner")
    with pytest.raises(FormError, match="is not one of the 14"):
        parse_form(form.replace(items[0]["id"], "0123456789", 1), items, "owner")


def test_text_that_looks_like_a_label_inside_the_paper_text_is_not_read_as_an_answer():
    items = [dict(_items()[0], sentence="ANSWER: yes was the label here")]
    form = render_form(items, INTRO, "owner")
    with pytest.raises(FormError, match="ANSWER is empty"):
        parse_form(form, items, "owner")


def test_missing_ai_line_is_only_a_warning():
    items = _items()
    form = _fill(render_form(items, INTRO, "owner"), {i: "yes" for i in range(1, 15)})
    form = form.replace("AI ASSISTANCE (no / yes, describe): no", "")
    _, meta = parse_form(form, items, "owner")
    assert any("AI ASSISTANCE" in w for w in meta["warnings"])


def test_highlight_marks_the_estimates_numbers_only():
    assert highlight("by 3.1 WU, 95% CI 1.1 to 5.7 WU, p=0.014", [3.1, 1.1, 5.7]) == "by [[3.1]] WU, 95% CI [[1.1]] to [[5.7]] WU, p=0.014"
    assert highlight("OR 0.50 (-0.30)", [0.5, 0.3]) == "OR [[0.50]] ([[-0.30]])"
