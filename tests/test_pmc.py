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
