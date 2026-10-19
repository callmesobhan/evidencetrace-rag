import hashlib
import xml.etree.ElementTree as ET

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

