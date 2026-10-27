import hashlib
import http.client
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from evidencetrace.ingest.pmc import (
    UnsafeXML,
    is_permissive,
    license_of,
    manifest_row,
    pmcid_of,
    split_articles,
    split_for,
)


def article(pmcid="12345", href="https://creativecommons.org/licenses/by/4.0/", body=True):
    lic = f'<license xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="{href}"><license-p>x</license-p></license>' if href else ""
    return (
        f'<article><front><article-meta><article-id pub-id-type="pmcid">PMC{pmcid}</article-id>'
        f"<title-group><article-title>A <italic>trial</italic></article-title></title-group>"
        f"<pub-date><year>2022</year></pub-date><permissions>{lic}</permissions></article-meta>"
        f"<journal-meta><journal-title-group><journal-title>J Test</journal-title></journal-title-group></journal-meta>"
        f"</front>{'<body><p>x</p></body>' if body else ''}</article>"
    )


@pytest.mark.parametrize(
    "href, ok",
    [
        ("https://creativecommons.org/licenses/by/4.0/", True),
        ("http://creativecommons.org/licenses/by/3.0", True),
        ("https://creativecommons.org/publicdomain/zero/1.0/", True),
        ("https://creativecommons.org/licenses/by-nc/4.0/", False),
        ("https://creativecommons.org/licenses/by-nd/4.0/", False),
        ("https://creativecommons.org/licenses/by-sa/4.0/", False),
        (None, False),
    ],
)
def test_licence_filter(href, ok):
    art = ET.fromstring(article(href=href))
    assert is_permissive(license_of(art)) is ok


def test_licence_found_in_license_p_text():
    art = ET.fromstring(
        "<article><license><license-p>Licensed under https://creativecommons.org/licenses/by/4.0/.</license-p></license></article>"
    )
    assert is_permissive(license_of(art))


def test_pmcid_normalisation_and_manifest():
    art = ET.fromstring(article("777"))
    assert pmcid_of(art) == "PMC777"
    row = manifest_row("PMC777", art, "q")
    assert (row.title, row.journal, row.year) == ("A trial", "J Test", "2022")
    assert row.license.startswith("creativecommons.org/licenses/by/")
    assert row.split in {"dev", "test"}


def test_split_articles_handles_batches_and_rejects_entities():
    batch = f"<pmc-articleset>{article('1')}{article('2')}</pmc-articleset>"
    assert [p for p, _ in split_articles(batch)] == ["PMC1", "PMC2"]
    with pytest.raises(UnsafeXML):
        split_articles('<!DOCTYPE x [<!ENTITY a "b">]><pmc-articleset/>')


def test_split_is_deterministic_and_roughly_balanced():
    ids = [f"PMC{i}" for i in range(2000)]
    assert [split_for(i) for i in ids] == [split_for(i) for i in ids]
    dev = sum(split_for(i) == "dev" for i in ids)
    assert 900 < dev < 1100


# ------------------------------------------------------------------ pinned fetch: metadata churn is not drift, content change is
def _article(extra_event_date: str = "2024-06-14 11:25:14.610", body: str = "The hazard ratio was 0.80 (95% CI 0.70 to 0.91)."):
    xml = (
        "<article><front><article-meta>"
        "<article-id pub-id-type=\"pmcid\">PMC9999999</article-id>"
        "<title-group><article-title>Synthetic paper</article-title></title-group>"
        "<pub-history><event event-type=\"pmc-last-change\"><date iso-8601-date=\"" + extra_event_date + "\">"
        "<day>14</day><month>06</month><year>2024</year></date></event></pub-history>"
        "</article-meta></front><body><sec><title>Results</title><p>" + body + "</p></sec></body></article>"
    )
    return ET.fromstring(xml)


def test_metadata_only_change_is_accepted_but_content_change_is_drift():
    from evidencetrace.ingest.pmc import canonical_sha256, check_fetched

    original = _article()
    pin = {"pmcid": "PMC9999999", "sha256": hashlib.sha256(ET.tostring(original, encoding="unicode").encode("utf-8")).hexdigest()}
    canon = canonical_sha256(original)
    assert check_fetched(_article(), pin, canon) == "ok"
    # PMC re-processes the record: only the last-change event date moves
    assert check_fetched(_article(extra_event_date="2026-10-18 16:54:36.100"), pin, canon) == "metadata"
    # the article's text changes: the results could change, so this is drift
    assert check_fetched(_article(body="The hazard ratio was 0.82 (95% CI 0.70 to 0.91)."), pin, canon) == "drifted"
    # no canonical pin for this paper: a raw change can only be reported as drift
    assert check_fetched(_article(extra_event_date="2026-10-18 16:54:36.100"), pin, None) == "drifted"


def test_canonical_hash_ignores_pmc_bookkeeping_but_not_text():
    from evidencetrace.ingest.pmc import canonical_sha256

    assert canonical_sha256(_article()) == canonical_sha256(_article(extra_event_date="2026-10-18 16:54:36.100"))
    assert canonical_sha256(_article()) != canonical_sha256(_article(body="Something else."))


def test_ncbi_error_pages_are_retried_and_a_persistent_error_is_reported(monkeypatch):
    from evidencetrace.ingest import pmc

    monkeypatch.setattr(pmc.time, "sleep", lambda _s: None)
    html = "<!DOCTYPE html><html><title>NCBI/eutils WWW Error 500</title></html>"
    answers = iter([html, html, "<PubmedArticleSet/>"])
    monkeypatch.setattr(pmc, "_get", lambda url, params, retries=3: next(answers))
    assert pmc._get_xml("u", {}, roots={"PubmedArticleSet"}) == "<PubmedArticleSet/>"

    monkeypatch.setattr(pmc, "_get", lambda url, params, retries=3: html)
    import pytest as _pytest

    with _pytest.raises(RuntimeError, match="did not return XML"):
        pmc._get_xml("u", {}, roots={"PubmedArticleSet"}, attempts=3)


@pytest.mark.parametrize("failure", [lambda: http.client.IncompleteRead(b"x" * 10), lambda: ConnectionResetError("reset"),
                                     lambda: TimeoutError("timed out")])
def test_a_truncated_or_dropped_response_is_retried(monkeypatch, failure):
    from evidencetrace.ingest import pmc

    class Resp:
        def __init__(self, fail):
            self.fail = fail

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            if self.fail:
                raise failure()
            return b"<PubmedArticleSet/>"

    monkeypatch.setattr(pmc.time, "sleep", lambda _s: None)
    calls = iter([Resp(True), Resp(True), Resp(False)])
    monkeypatch.setattr(pmc.urllib.request, "urlopen", lambda req, timeout=60: next(calls))
    assert pmc._get_xml("https://example.invalid", {}, roots={"PubmedArticleSet"}) == "<PubmedArticleSet/>"


def _pin_for(art: ET.Element) -> dict:
    return {"pmcid": art.find(".//article-id[@pub-id-type='pmcid']").text,
            "sha256": hashlib.sha256(ET.tostring(art, encoding="unicode").encode("utf-8")).hexdigest()}


def test_fetch_pinned_checks_papers_on_disk_without_network(tmp_path, monkeypatch):
    from evidencetrace.ingest import pmc

    art = _article()
    (tmp_path / "PMC9999999.xml").write_text(ET.tostring(art, encoding="unicode"), encoding="utf-8")

    def no_network(ids):
        raise AssertionError("a paper already on disk must not be requested from NCBI")

    monkeypatch.setattr(pmc, "efetch", no_network)
    res = pmc.fetch_pinned([_pin_for(art)], tmp_path, sleep=0, log=lambda _m: None)
    assert res["ok"] == ["PMC9999999"] and res["fetched"] == [] and res["missing"] == []


def test_fetch_pinned_downloads_only_what_is_not_on_disk(tmp_path, monkeypatch):
    from evidencetrace.ingest import pmc

    on_disk, missing = _article(), _article()
    missing.find(".//article-id[@pub-id-type='pmcid']").text = "PMC9999998"
    (tmp_path / "PMC9999999.xml").write_text(ET.tostring(on_disk, encoding="unicode"), encoding="utf-8")
    asked = []

    def fake_efetch(ids):
        asked.append(list(ids))
        return "<pmc-articleset>" + ET.tostring(missing, encoding="unicode") + "</pmc-articleset>"

    monkeypatch.setattr(pmc, "efetch", fake_efetch)
    res = pmc.fetch_pinned([_pin_for(on_disk), _pin_for(missing)], tmp_path, sleep=0, log=lambda _m: None)
    assert asked == [["9999998"]]
    assert res["ok"] == ["PMC9999999", "PMC9999998"] and res["fetched"] == ["PMC9999998"]
    assert (tmp_path / "PMC9999998.xml").exists()


def test_committed_papers_match_their_pins_offline():
    """Every paper the manifests list and that is not in data/raw/excluded.json must be committed and must verify against its pin."""
    import json

    from evidencetrace.ingest.pmc import check_on_disk

    root = Path(__file__).resolve().parent.parent
    doc = json.loads((root / "data" / "raw" / "excluded.json").read_text(encoding="utf-8"))
    not_committed = {e["pmcid"]: e for e in doc["excluded"]}
    canonical = {r["pmcid"]: r["canonical_sha256"] for r in map(json.loads, (root / "data/m1/canonical_pins.jsonl").read_text().splitlines())}
    for e in doc["excluded"]:
        assert e["licence_statement"] and e["copyright_line"] and e["reason"], e["pmcid"]
    checked = 0
    for manifest, raw in (("corpus_manifest.jsonl", "pmc"), ("fresh_manifest.jsonl", "fresh")):
        for ln in (root / "data" / "m1" / manifest).read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            pin = json.loads(ln)
            if pin["pmcid"] in not_committed:
                assert not_committed[pin["pmcid"]]["dir"] == f"data/raw/{raw}", pin["pmcid"]
                continue
            path = root / "data" / "raw" / raw / f"{pin['pmcid']}.xml"
            assert path.exists(), f"{path} is not committed and not excluded"
            assert check_on_disk(path, pin, canonical.get(pin["pmcid"])) in ("ok", "metadata"), pin["pmcid"]
            checked += 1
    assert checked == 164

