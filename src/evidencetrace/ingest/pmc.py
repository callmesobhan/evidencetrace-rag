"""Acquire open-access full text from PubMed Central (NCBI E-utilities), keeping only permissive licences.

Why the licence filter: gold files quote short snippets of the papers, and the repo should be able to
say where every snippet came from and under what terms. Only CC BY and CC0 are kept; NC/ND/SA and
anything with no machine-readable licence are dropped and counted.

Safety: downloaded XML is untrusted input. Documents that declare XML entities are rejected before
parsing (entity-expansion attacks), and external DTDs are never fetched by ElementTree.

Courtesy: NCBI asks for <= 3 requests/second without an API key and a ``tool`` parameter. No e-mail
address is sent.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "evidencetrace-rag"
PERMISSIVE_LICENSES = ("creativecommons.org/licenses/by/", "creativecommons.org/publicdomain/zero/")
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


class UnsafeXML(ValueError):
    pass


def reject_unsafe_xml(text: str) -> None:
    if "<!ENTITY" in text:
        raise UnsafeXML("document declares XML entities; refusing to parse")


def pmcid_of(article: ET.Element) -> str | None:
    for aid in article.iter("article-id"):
        if aid.get("pub-id-type") in {"pmcid", "pmc", "pmcaid"} and aid.text:
            digits = re.sub(r"\D", "", aid.text)
            if digits:
                return f"PMC{digits}"
    return None


def license_of(article: ET.Element) -> str | None:
    """Normalised licence URL (lower-case, no scheme), or None if the article states none."""
    for lic in article.iter("license"):
        candidates = [lic.get(_XLINK_HREF), lic.get("href")]
        candidates += [el.get(_XLINK_HREF) for el in lic.iter("ext-link")]
        candidates += re.findall(r"https?://\S+", " ".join(lic.itertext()))
        for href in candidates:
            if href and "creativecommons.org" in href:
                return re.sub(r"^https?://(www\.)?", "", href.strip().lower()).rstrip(".,;)/") + "/"
    return None


def is_permissive(license_url: str | None) -> bool:
    return bool(license_url) and any(license_url.startswith(p) for p in PERMISSIVE_LICENSES)


def split_for(pmcid: str, dev_fraction: float = 0.5) -> str:
    """Deterministic dev/test assignment from the id alone, so the split is fixed before any tuning."""
    h = int(hashlib.sha1(pmcid.encode()).hexdigest()[:8], 16) / 16**8
    return "dev" if h < dev_fraction else "test"


def _text(el: ET.Element | None) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


@dataclass
class ManifestRow:
    pmcid: str
    title: str
    journal: str
    year: str
    license: str
    split: str
    query: str
    article_type: str = ""


def split_articles(batch_xml: str) -> list[tuple[str, ET.Element]]:
    reject_unsafe_xml(batch_xml)
    root = ET.fromstring(batch_xml)
    articles = [root] if root.tag == "article" else root.findall("article")
    out = []
    for art in articles:
        pmcid = pmcid_of(art)
        if pmcid:
            out.append((pmcid, art))
    return out


def manifest_row(pmcid: str, art: ET.Element, query: str) -> ManifestRow:
    year = ""
    for pd in art.iter("pub-date"):
        y = pd.findtext("year")
        if y:
            year = y
            break
    return ManifestRow(
        pmcid=pmcid,
        title=_text(art.find(".//article-title")),
        journal=_text(art.find(".//journal-title")),
        year=year,
        license=license_of(art) or "",
        split=split_for(pmcid),
        query=query,
        article_type=art.get("article-type") or "",
    )


# ----------------------------------------------------------------------------- network
def _get(url: str, params: dict[str, str], *, retries: int = 3) -> str:
    full = f"{url}?{urllib.parse.urlencode({**params, 'tool': TOOL})}"
    req = urllib.request.Request(full, headers={"User-Agent": f"{TOOL}/0.1"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503} or attempt == retries - 1:
                raise
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def esearch(query: str, retmax: int, *, db: str = "pmc") -> list[str]:
    term = f"({query}) AND open access[filter]" if db == "pmc" else query
    raw = _get(f"{EUTILS}/esearch.fcgi", {"db": db, "term": term, "retmax": str(retmax),
                                          "retmode": "json", "sort": "relevance"})
    return json.loads(raw)["esearchresult"]["idlist"]


def pubmed_rct_to_pmc(query: str, retmax: int, *, sleep: float = 0.4) -> list[str]:
    """PubMed has a real publication-type index; PMC does not. Search PubMed for RCTs, link to PMC.

    (A ``[Publication Type]`` clause sent to PMC silently degrades to a full-text keyword match,
    which in our first attempt returned a corpus that was more than half review articles.)
    """
    pmids = esearch(f"({query}) AND randomized controlled trial[pt]", retmax, db="pubmed")
    pmc_ids: list[str] = []
    for i in range(0, len(pmids), 100):
        time.sleep(sleep)
        raw = _get(f"{EUTILS}/elink.fcgi", {"dbfrom": "pubmed", "db": "pmc", "linkname": "pubmed_pmc",
                                            "id": ",".join(pmids[i : i + 100]), "retmode": "json"})
        for ls in json.loads(raw).get("linksets", []):
            for db in ls.get("linksetdbs", []):
                pmc_ids += [str(x) for x in db.get("links", [])]
    return list(dict.fromkeys(pmc_ids))  # de-duplicate, keep order


def pubmed_publication_types(pmids: list[str], *, batch: int = 100, sleep: float = 0.4) -> dict[str, list[str]]:
    """PubMed's publication types for each PMID (one polite request per ``batch`` ids)."""
    from evidencetrace.ingest.design import parse_publication_types

    out: dict[str, list[str]] = {}
    for i in range(0, len(pmids), batch):
        if i:
            time.sleep(sleep)
        raw = _get(f"{EUTILS}/efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids[i : i + batch]), "retmode": "xml"})
        out.update(parse_publication_types(raw))
    return out


def efetch(ids: list[str]) -> str:
    return _get(f"{EUTILS}/efetch.fcgi", {"db": "pmc", "id": ",".join(ids), "rettype": "xml"})


def fetch_corpus(
    query: str,
    out_dir: Path,
    *,
    target: int,
    max_ids: int,
    batch_size: int = 20,
    sleep: float = 0.4,
    source: str = "pubmed_rct",
    article_types: tuple[str, ...] = ("research-article",),
    exclude: set[str] | None = None,
    split_label: str | None = None,
    log: Callable[[str], None] = print,
) -> list[ManifestRow]:
    """Fetch until ``target`` permissively-licensed articles are on disk (or ids run out).

    ``source``: "pubmed_rct" (PubMed RCT publication type, linked to PMC) or "pmc" (PMC keyword search).
    ``article_types``: JATS ``article-type`` values to keep; reviews/editorials are counted and dropped.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"
    rows: dict[str, ManifestRow] = {}
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            r = ManifestRow(**json.loads(line))
            rows[r.pmcid] = r

    ids = pubmed_rct_to_pmc(query, max_ids) if source == "pubmed_rct" else esearch(query, max_ids)
    skip = exclude or set()
    ids = [i for i in ids if f"PMC{i}" not in rows and f"PMC{i}" not in skip]
    log(f"search: {len(ids)} new candidate ids ({len(skip)} excluded)")
    dropped = {"license": 0, "unsafe": 0, "no_body": 0, "article_type": 0}
    for i in range(0, len(ids), batch_size):
        if len(rows) >= target:
            break
        time.sleep(sleep)
        batch = ids[i : i + batch_size]
        try:
            articles = split_articles(efetch(batch))
        except UnsafeXML:
            dropped["unsafe"] += len(batch)
            continue
        for pmcid, art in articles:
            if pmcid in rows:
                continue
            lic = license_of(art)
            if not is_permissive(lic):
                dropped["license"] += 1
                continue
            if art.get("article-type") not in article_types:
                dropped["article_type"] += 1
                continue
            if art.find(".//body") is None:
                dropped["no_body"] += 1
                continue
            (out_dir / f"{pmcid}.xml").write_text(ET.tostring(art, encoding="unicode"), encoding="utf-8")
            row = manifest_row(pmcid, art, query)
            if split_label:
                row.split = split_label
            rows[pmcid] = row
        manifest_path.write_text(
            "\n".join(json.dumps(asdict(r), ensure_ascii=False) for r in rows.values()) + "\n",
            encoding="utf-8",
        )
        log(f"  fetched {min(i + batch_size, len(ids))}/{len(ids)} ids -> kept {len(rows)}  dropped {dropped}")
    return list(rows.values())


# ----------------------------------------------------------------------------- pinned corpus
def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_manifest(raw_dir: Path) -> list[dict]:
    """Manifest rows + the SHA-256 of each stored XML, so the corpus can be re-downloaded and *checked*."""
    rows = []
    for ln in (raw_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        row = json.loads(ln)
        f = raw_dir / f"{row['pmcid']}.xml"
        row["sha256"], row["bytes"] = sha256_file(f), f.stat().st_size
        rows.append(row)
    return rows


def fetch_pinned(
    pinned: list[dict],
    out_dir: Path,
    *,
    batch_size: int = 20,
    sleep: float = 0.4,
    allow_drift: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, list[str]]:
    """Download exactly the pinned PMCIDs and verify each file against its recorded hash.

    Returns {"ok": [...], "drifted": [...], "missing": [...]}. Drift means PMC now serves different XML
    for that id (publishers correct papers); gold quotes may then no longer match, so by default a
    drifted file is NOT written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    want = {r["pmcid"]: r for r in pinned}
    result: dict[str, list[str]] = {"ok": [], "drifted": [], "missing": []}
    ids = [r["pmcid"] for r in pinned]
    for i in range(0, len(ids), batch_size):
        time.sleep(sleep)
        batch = ids[i : i + batch_size]
        got = dict(split_articles(efetch([b.removeprefix("PMC") for b in batch])))
        for pmcid in batch:
            art = got.get(pmcid)
            if art is None:
                result["missing"].append(pmcid)
                continue
            text = ET.tostring(art, encoding="unicode")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest == want[pmcid]["sha256"]:
                (out_dir / f"{pmcid}.xml").write_text(text, encoding="utf-8")
                result["ok"].append(pmcid)
            else:
                result["drifted"].append(pmcid)
                if allow_drift:
                    (out_dir / f"{pmcid}.xml").write_text(text, encoding="utf-8")
        log(f"  {min(i + batch_size, len(ids))}/{len(ids)}  ok={len(result['ok'])} "
            f"drifted={len(result['drifted'])} missing={len(result['missing'])}")
    (out_dir / "manifest.jsonl").write_text(
        "\n".join(json.dumps({k: v for k, v in want[p].items() if k not in {"sha256", "bytes"}}, ensure_ascii=False)
                  for p in result["ok"] + (result["drifted"] if allow_drift else [])) + "\n",
        encoding="utf-8",
    )
    return result
