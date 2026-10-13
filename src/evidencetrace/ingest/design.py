"""Study-design screening from PubMed's publication types and explicit title phrases.

The M1 corpus was fetched with a query that asked for randomized trials, but PMC's ``article_type`` is
``research-article`` for everything and PubMed's own tagging is imperfect, so the design of each paper was never
checked. This module classifies it from two independent signals and keeps both, so a disagreement is visible:

* ``pubmed_types``: the publication types PubMed assigns to the record (curated by NLM indexers or the publisher).
* title phrases that name a design outright ("meta-analysis", "cohort study", "study protocol", "cost-effectiveness").

It is a screen, not a ruling: a human should read the ``disagree`` rows.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

SYNTHESIS_PT = {"meta-analysis", "systematic review", "review"}
OBSERVATIONAL_PT = {"observational study"}
_TRIAL_PT_PREFIX = ("clinical trial", "controlled clinical trial", "pragmatic clinical trial", "equivalence trial")

SYNTH_TITLE = re.compile(r"meta-?analys|systematic review|network meta|umbrella review|scoping review", re.I)
# "pooled analysis of the X and Y trials" / "individual patient data" usually describe the trials' OWN data, which PubMed
# labels a randomized trial; they count as evidence synthesis only when PubMed does not call the paper a trial.
WEAK_SYNTH_TITLE = re.compile(r"pooled analysis|individual[- ](?:patient|participant)", re.I)
PROTOCOL_TITLE = re.compile(r"(?:study|trial|research|clinical)\s+protocol|protocol (?:for|of)\b|rationale and design|design and rationale", re.I)
ECON_TITLE = re.compile(r"cost[- ]effective|cost[- ]utility|economic evaluation|budget impact", re.I)
OBS_TITLE = re.compile(r"cohort study|cross-sectional|case[- ]control|mendelian randomi[sz]ation|retrospective (?:study|analysis|cohort)|"
                       r"prospective (?:cohort|observational)|observational (?:study|analysis)|real-world", re.I)

TRIAL = "trial"


def classify_design(pubmed_types: list[str], title: str) -> tuple[str, str, bool]:
    """(design, basis, disagree).

    ``design`` is one of trial / evidence_synthesis / protocol / economic_evaluation / observational / other.
    ``basis`` says which signal decided it. ``disagree`` is True when PubMed calls it a trial but the title names another
    design (or vice versa), the rows a human should look at.
    """
    t = {x.lower() for x in pubmed_types}
    is_protocol_pt = "clinical trial protocol" in t
    pubmed_trial = not is_protocol_pt and ("randomized controlled trial" in t or any(x.startswith(_TRIAL_PT_PREFIX) for x in t))
    if t & SYNTHESIS_PT or SYNTH_TITLE.search(title) or (WEAK_SYNTH_TITLE.search(title) and not pubmed_trial):
        design, basis = "evidence_synthesis", "pubmed" if t & SYNTHESIS_PT else "title"
    elif is_protocol_pt or PROTOCOL_TITLE.search(title):
        design, basis = "protocol", "pubmed" if is_protocol_pt else "title"
    elif ECON_TITLE.search(title):
        design, basis = "economic_evaluation", "title"
    elif t & OBSERVATIONAL_PT or OBS_TITLE.search(title):
        design, basis = "observational", "pubmed" if t & OBSERVATIONAL_PT else "title"
    elif pubmed_trial:
        design, basis = TRIAL, "pubmed"
    else:
        design, basis = "other", "none"
    return design, basis, (design != TRIAL and pubmed_trial) or (design == TRIAL and not pubmed_trial)


def pmid_of(jats_xml: str) -> str | None:
    m = re.search(r'<article-id[^>]*pub-id-type="pmid"[^>]*>(\d+)<', jats_xml)
    return m.group(1) if m else None


def parse_publication_types(pubmed_xml: str) -> dict[str, list[str]]:
    """{pmid: [publication type, ...]} from a PubMed efetch response."""
    if "<!ENTITY" in pubmed_xml:
        raise ValueError("PubMed response declares XML entities; refusing to parse")
    root = ET.fromstring(pubmed_xml)
    out: dict[str, list[str]] = {}
    for art in root.iter("PubmedArticle"):
        pmid = art.findtext("MedlineCitation/PMID")
        if pmid:
            out[pmid] = ["".join(pt.itertext()).strip() for pt in art.iter("PublicationType")]
    return out
