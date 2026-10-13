"""Text normalisation shared by retrieval, verification and conflict matching."""

from __future__ import annotations

import re
import unicodedata

# Words that carry no topical signal in an evidence query. Directional verbs are included on
# purpose: "does X reduce Y" and "does X increase Y" are the same question.
STOPWORDS = frozenset(
    """a an the of on in for to with and or by at from as is are was were be been does do did
    what which who how much many any there their it its this that these those than
    effect effects effective effectiveness efficacy impact influence association associated
    compared compare comparison
    versus vs relative reduce reduces reduced reducing lower lowers lowered lowering
    decrease decreased decreases increase increased increases improve improved improves
    raise raised raises change changed changes affect affected affects patients patient""".split()
)

# Tiny seed list. A real deployment should link to MeSH/UMLS instead (see docs/roadmap.md).
SYNONYMS: dict[str, list[str]] = {
    "bp": ["blood", "pressure"],
    "sbp": ["systolic", "blood", "pressure"],
    "dbp": ["diastolic", "blood", "pressure"],
    "mi": ["myocardial", "infarction"],
    "hf": ["heart", "failure"],
    "cvd": ["cardiovascular", "disease"],
    "t2dm": ["type", "2", "diabetes"],
}

_TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
_SUFFIXES = (
    "izations", "ization", "isations", "isation", "izing", "ising", "ized", "ised",
    "ings", "ing", "ed", "es", "s",
)  # fmt: skip


# Lancet-style decimals ("0·78", "2·5"): a middle dot between digits is a decimal point. A dot followed by digits and
# then a letter ("Cl12·24H2O") is chemistry, not a number, and is left alone.
_MIDDLE_DOT_DECIMAL = re.compile(r"(?<=\d)\u00b7(?=\d+(?![\dA-Za-z]))")
# C0/C1 control characters except tab and newline: they let a quoted passage drive a terminal (escape sequences)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def canonical_text(raw: str) -> str:
    """The text every offset in the system refers to. Change this and all offsets change."""
    text = unicodedata.normalize("NFKC", raw).replace("\ufeff", "")  # also drops a UTF-8 byte-order mark
    text = _MIDDLE_DOT_DECIMAL.sub(".", text)
    # hyphen variants (U+2010-2012) -> "-": "0.31\u20101.69" is a range, and tokens like self\u2010care unify
    text = text.replace("\u2010", "-").replace("\u2011", "-").replace("\u2012", "-")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_CHARS.sub("", text)


def stem(token: str) -> str:
    """Deliberately tiny stemmer: enough to match hospitalization/hospitalised/hospitalizations."""
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[: -len(suffix)] + ("iz" if suffix.startswith(("iz", "is")) else "")
            break
    if token.endswith("e") and len(token) > 4:
        token = token[:-1]
    return token


def tokenize(
    text: str, *, synonyms: dict[str, list[str]] | None = None, drop_stop: bool = True
) -> list[str]:
    syn = SYNONYMS if synonyms is None else synonyms
    out: list[str] = []
    for raw in _TOKEN.findall(text.lower()):
        # "semaglutide-treated" must match a query for "semaglutide": keep the compound AND its parts
        pieces = [raw] + (re.split(r"[-']", raw) if re.search(r"[-']", raw) else [])
        for piece in pieces:
            for tok in syn.get(piece, [piece]):
                if drop_stop and tok in STOPWORDS:
                    continue
                out.append(stem(tok))
    return out


def normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def jaccard(a: set[str] | list[str], b: set[str] | list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)
