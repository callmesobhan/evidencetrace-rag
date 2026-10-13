"""Mechanical provenance checks.

A Finding is only allowed into an answer if it can be re-derived from the source text:
 - the document it points at is byte-identical to the one it was extracted from (sha256),
 - ``text[start:end]`` is exactly the quoted span,
 - every number it reports (value, CI bounds, p, n) literally occurs in that span,
 - the intervention / outcome / comparator strings occur in that span.

These checks do not trust the extractor, so they also catch a BERT/LLM extractor that
"normalises" or hallucinates a number.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from evidencetrace.config import VerificationConfig
from evidencetrace.ingest.document import Document
from evidencetrace.schemas import Finding, VerificationResult
from evidencetrace.textnorm import normalize_phrase

# A sign counts only when it is not glued to a preceding digit: "0.65-0.93" is a range, "-0.93" is not.
_NUMBER = re.compile(r"(?<![\d.%])(?P<sign>[-\u2212\u2013]\s?)?(?P<num>\d+(?:\.\d+)?|\.\d+)")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_SCI = re.compile(r"(?P<m>\d+(?:\.\d+)?)\s*[×x*]\s*10\s*[-\u2212\u2013]?\s*(?P<e>\d+)")


def numbers_in(text: str) -> list[float]:
    """All numbers a reader could take from ``text``.

    A true minus sign (U+2212) or an ASCII hyphen/en dash glued to the digits is a sign. A hyphen or
    en dash followed by a *space* ("- 0.93") is ambiguous - a range separator or a spaced minus - so
    both readings are accepted. That keeps ``0.65 - 0.93`` verifiable without letting a flipped sign
    pass against an unambiguous ``\u22126.0``.
    """
    cleaned = _THOUSANDS.sub("", text)
    # "1.02 x 10-6"; an exponent written without a sign is read as negative (nobody reports p = 1e+6)
    out: list[float] = [float(m["m"]) * 10 ** -int(m["e"]) for m in _SCI.finditer(cleaned)]
    for m in _NUMBER.finditer(cleaned):
        x = float(m["num"])
        sign = m["sign"]
        if not sign:
            out.append(x)
        elif sign.strip() == "\u2212" or not sign.endswith(" "):
            out.append(-x)  # unambiguous minus (or glued hyphen)
        else:
            out += [-x, x]  # "- 0.93": spaced minus or range separator
    return out


def number_in_text(x: float, text: str, *, tol: float = 1e-9) -> bool:
    # relative tolerance too: p = 2.01e-5 must not match 2.02e-5, and 1e-10 must not match 2e-10
    return any(math.isclose(x, y, rel_tol=1e-9, abs_tol=min(tol, abs(x) * 1e-6)) for y in numbers_in(text))


class Verifier:
    def __init__(self, docs: Mapping[str, Document], cfg: VerificationConfig | None = None):
        self._docs = docs
        self._cfg = cfg or VerificationConfig()

    def verify(self, f: Finding) -> VerificationResult:
        checks: dict[str, bool] = {}
        doc = self._docs.get(f.doc_id)
        checks["document_present"] = doc is not None
        if doc is None:
            return VerificationResult(finding_id=f.finding_id, checks=checks)

        checks["document_unchanged"] = doc.sha256 == f.doc_sha256
        source = doc.text[f.span.start : f.span.end]
        checks["span_text_matches"] = source == f.span.text

        checks["value_in_span"] = number_in_text(f.value, source)
        if f.ci is not None:
            checks["ci_in_span"] = number_in_text(f.ci.low, source) and number_in_text(
                f.ci.high, source
            )
        if f.p_value is not None:
            checks["p_in_span"] = number_in_text(f.p_value, source)
        if f.n is not None:
            checks["n_in_span"] = number_in_text(float(f.n), source)

        if self._cfg.require_fields_in_span:
            haystack = normalize_phrase(source)
            for name in ("intervention", "comparator", "outcome", "population"):
                value = getattr(f, name)
                if value:
                    checks[f"{name}_in_span"] = normalize_phrase(value) in haystack
        return VerificationResult(finding_id=f.finding_id, checks=checks)
