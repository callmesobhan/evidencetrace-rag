"""High-precision mining of quantitative effect estimates from a single sentence.

This layer only finds *numbers and their statistical type*. Who/what the numbers are about
(intervention, outcome, comparator) is the job of a FieldTagger. Keeping the split means the
numeric side can be near-deterministic while the semantic side is swappable (rules -> BERT).

Structure: HEAD (metric name + point estimate [+ unit]) followed by exactly one TAIL form:

    labelled   HR 0.78 (95% CI 0.65-0.93)   HR 0.78, 95% CI [0.65, 0.93]   MD 3.1 mL [CI, -2 to 8]
    bare       HR 0.82 (0.62-1.10; p=0.01)  OR 1.5 [1.1, 2.0]
    comma      RR 2.48, 1.36-4.52, I2 = 65%
    (none)     HR 0.78 (p=0.006)            -> an estimate with no interval

and optionally a *continuation* list that reuses the metric:

    HR 0.80 (0.66-0.97) for MI, 0.71 (0.66-0.77) for stroke, and 0.68 (0.54-0.85) for HF

Every candidate must pass sanity checks (point estimate inside its own interval, ratios positive and
unit-free, no decimal commas, not a power calculation) - a source typo or a planning sentence is
dropped or demoted rather than reported as a finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from evidencetrace.schemas import Metric

_DASH = "\\-\u2010\u2011\u2012\u2013\u2014\u2212"
NUM = r"[+\-\u2212\u2013]?\s?(?:\d+(?:\.\d+)?|\.\d+)"
VAL = r"[£$€]?[+\-\u2212\u2013]?\s?(?:\d+\.\d+(?!\d)|\.\d+(?!\d)|\d+(?!\d|\.\d|,\d))"  # whole token; "1,8" is a decimal comma
END = NUM + r"(?!\d|\.\d)"  # interval endpoint
SEP = rf"(?:to|and|[{_DASH}]|,|;)"
SEP_NOCOMMA = rf"(?:to|[{_DASH}])"
SEP_BARE = rf"(?:to|[{_DASH}]|,|;)"

# Full names are case-insensitive; abbreviations are case-SENSITIVE so "or" never reads as OR.
_METRIC_PATTERNS: list[tuple[Metric, str]] = [
    (Metric.SMD, r"standardi[sz]ed\s+mean\s+differences?|Cohen'?s?\s+d|Hedges'?\s+g|(?-i:SMDs?)"),
    # "mean difference", "mean between-group difference", "treatment group difference", "WMD", "AMD" ...
    (Metric.MD, r"mean\s+(?:[A-Za-z-]+\s+){0,4}?differences?"
                r"|(?:estimated\s+)?(?:treatment(?:\s+group)?|between[- ](?:group|time|arm)s?)\s+differences?"
                r"|difference\s+in\s+means?|(?-i:A?MDs?|WMDs?|LSMDs?)"),
    (Metric.HR, r"hazard\s+ratios?|(?-i:(?:[aA]?HRs?|SHRs?)(?:adj(?:usted)?|unadj(?:usted)?|crude)?)"),
    (Metric.IRR, r"incidence\s+rate\s+ratios?|rate\s+ratios?|(?-i:a?IRRs?)"),
    (Metric.OR, r"odds\s+ratios?|(?-i:(?:[aAuU]?ORs?)(?:adj(?:usted)?|unadj(?:usted)?|crude)?)"),
    (Metric.RR, r"relative\s+risks?|risk\s+ratios?|(?-i:(?:a?RRs?)(?:adj(?:usted)?|unadj(?:usted)?|crude)?)"),
    (Metric.RD, r"risk\s+differences?|absolute\s+risk\s+(?:reduction|difference)s?|absolute\s+difference\s+in\s+risk|(?-i:a?RDs?)"),
]
_METRIC_ALT = "|".join(f"(?P<m_{m.name}>{pat})" for m, pat in _METRIC_PATTERNS)

# Units we are confident about. Others are accepted only when an interval follows (see _extract).
_UNIT_WS = (
    r"mm\s?Hg|mg/dL|mmol/L|[µμ]mol/L|ng/mL|pg/mL|U/L|ml/min|kg/m2|bpm|kg|mg|mL|"
    r"percentage\s+points?|pp|points?|days?|weeks?|months?|years?|%"
)
_UNIT_GEN = (
    r"(?!(?:with|and|in|for|at|from|to|among|between|vs|versus|compared|CIs?|was|were|is|per|"
    r"favou?ring|p|the|of|on|by|than|or|as|when|after|before|during|which|that)\b)"
    r"[A-Za-zµμ°%][^\s;,()\[\]]{0,23}"
)

UNIT_GEN_RE = re.compile(rf"\s*(?P<u>{_UNIT_GEN})", re.IGNORECASE)

_PREP = r"(?:for|of|in|with|versus|vs\.?|between|over|at|across|during|after|from|within|compared\s+(?:with|to))"
_FILL_COMMA = r"(?:[^().;=:\[\]%]|(?<=\d)\.(?=\d)|(?<=\bvs)\.)"
_FILL_CHARS = r"(?:[^().;=:,\[\]%]|(?<=\d)\.(?=\d)|(?<=\bvs)\.)"
HEAD_RE = re.compile(
    rf"""
    (?<![A-Za-z])(?<!geometric\s)
    (?P<metric>{_METRIC_ALT})
    (?:\s*[\[(][^()\[\]]{{1,60}}[\])])?                                   # "rate ratio [RR] 0.52", "RD (a - b) was"
    (?:\s*\[\s*\d{{2}}(?:\.\d)?\s*%\s*CI\s*\])?                          # "WMD [95% CI]: -4.1"
    (?:\s*(?:with|and)\s+\d{{2}}(?:\.\d)?\s*%\s*(?:CIs?|confidence\s+intervals?))?  # "MD with 95% CI -6.46 [..]"
    (?:
        \s+{_PREP}\s+{_FILL_CHARS}{{1,100}}?(?=\s+(?:was|were|is|are)\b|\s*[=:])       # "... vs placebo in LVEF was 2.5"
      | \s+{_PREP}\s+{_FILL_COMMA}{{1,100}}?(?=\s+(?:was|were|is|are)\b)               # "... at Week 156 for CV death, MI, or stroke was -0.02"
      | (?P<fn2>\s+{_PREP}\s+(?=[A-Za-z]){_FILL_CHARS}{{1,100}}?(?<![+\-\u2212\u2013])(?=\s*,\s*[+\-\u2212\u2013]?\s?\.?\d))  # "... at week 52, -2.91"
      | (?P<fn>\s+{_PREP}\s+(?![+\-\u2212\u2013]){_FILL_CHARS}{{1,100}}?(?<![+\-\u2212\u2013])(?=\s+(?:of\s+)?[£$€]?[+\-\u2212\u2013]?\s?\.?\d))  # "... for LVEF 2.3%" (a sign is never filler)
      | \s+(?:[A-Za-z][A-Za-z0-9-]*\s+){{0,4}}?(?=(?:was|were|is|are)\b)               # "mean difference SBP was -4.4"
    )?
    [\s,:=]*(?:(?:of|was|were|is|are|calculated|estimated|reported|observed|found|to\s+be|as|about|approximately)[\s,:=]*)*
    (?P<value>{VAL})
    (?!\s*%?\s*(?:CIs?\b|confidence))                                     # "mean difference, 95% CI"
    (?:\s*(?P<unit_ws>{_UNIT_WS})(?![A-Za-z]))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_LABEL = r"(?:CIs?|CrIs?|HDIs?|confidence\s+intervals?|credible\s+intervals?|posterior\s+intervals?|highest\s+density\s+intervals?)(?:\s*[\[(](?:CI|CrI|HDI)[\])])?"
TAIL_LABELLED = re.compile(
    rf"""
    (?:\s+(?:compared\s+(?:with|to)|vs\.?|versus|for|in|between|favou?ring)\s+[^()\[\];=]{{1,60}}?)?
    [\s,;(\[]*
    (?:
        (?:(?P<level>\d{{2}}(?:\.\d)?)\s*%\s*)?{_LABEL}
      | (?P<level2>\d{{2}}(?:\.\d)?)\s*%(?=\s*[{_DASH}\d.])
    )
    [\s:,=]*[(\[]?\s*
    (?P<lo>{END})\s*%?\s*{SEP}\s*(?P<hi>{END})\s*%?
    """,
    re.IGNORECASE | re.VERBOSE,
)
TAIL_LABELLED_TIGHT = re.compile(  # for continuations: no filler words allowed
    rf"""
    [\s,;(\[]*
    (?:(?P<level>\d{{2}}(?:\.\d)?)\s*%\s*)?{_LABEL}
    [\s:,=]*[(\[]?\s*
    (?P<lo>{END})\s*%?\s*{SEP}\s*(?P<hi>{END})\s*%?
    """,
    re.IGNORECASE | re.VERBOSE,
)
TAIL_BARE = re.compile(
    rf"\s*[(\[]\s*(?P<lo>{END})\s*%?\s*{SEP_BARE}\s*(?P<hi>{END})\s*%?\s*(?=[;)\]])"
)
TAIL_COMMA = re.compile(rf",\s*(?P<lo>{END})\s*{SEP_NOCOMMA}\s*(?P<hi>{END})(?=[\s,;)\]]|$)")
# what may sit between one list item's interval and the next item: "; P = .02) for MI,"
SKIP_AFTER_TAIL = re.compile(
    r"(?:\s*[;,]\s*[pP]\s*(?:<=|>=|[<>=≤≥])\s*(?:\d*\.\d+|\d+(?:\.\d+)?))?[\s)\]]*"
    r"(?:(?:for|in|among|with|respectively)\s+[^,;()\[\]]{1,50}?(?=\s*[,;]|\s+and\s))?"
)
CONT_RE = re.compile(
    rf"(?:\s*[,;]\s*(?:and\s+)?|\s*\b(?:and|or|vs\.?|versus)\s+)(?P<value>{VAL})(?:\s*(?P<unit_ws>{_UNIT_WS})(?![A-Za-z]))?"
)

P_RE = re.compile(
    r"(?<![A-Za-z])[pP]\s*(?:[- ]?value)?\s*(?P<op><=|>=|[<>=≤≥])\s*"
    r"(?:(?P<ten>10)(?![\d.])\s*\^?\s*(?P<tsign>[-\u2212\u2013])\s*(?P<texp>\d+)(?!\d)"  # "P < 10-4", "p<10^-4"
    r"|(?P<val>(?:\d*\.\d+|\d+(?:\.\d+)?)(?:[eE][-+\u2212]?\d+)?))"  # "3.1e-4"
    r"(?:\s*[×x*]\s*10\s*\^?\s*(?P<esign>[-\u2212\u2013])?\s*(?P<exp>\d+))?"  # "1.02 x 10-6", "1.2 x 10^-5"
)
# p-values that belong to something other than the estimate they sit next to
_P_NOT_EFFECT_AFTER = re.compile(r"\s*(?:for\s+)?(?:interaction|trend|heterogeneity)\b", re.I)
_P_NOT_EFFECT_BEFORE = re.compile(r"(?:I2|I²|Chi2|χ2|Q\s*=|heterogeneity|interaction)[^;)\]]{0,30}$", re.I)
DOI_AFTER = re.compile(r"[-\u2212]\s?10\.\d{4,}/")  # "RR2-10.1186/s13063-..." is a citation id
WITHIN_ARM_RE = re.compile(
    r"within[- ](?:the\s+)?(?:\w+\s+){0,2}(?:group|arm)s?\b|within[- ]group"
    r"|compared\s+(?:with|to)\s+(?:their|its|his|her)\s+(?:own\s+)?baseline",
    re.I,
)
# "mean difference (SD) ... was -0.23 (9.1)": the parenthesis is a standard deviation, not an interval
SD_LABEL_AFTER = re.compile(r"\s*\((?:SD|SE|SEM|IQR|standard\s+deviation)\)", re.I)
# An SMD quoted to show that two cohorts are alike at baseline is a balance diagnostic, not an effect:
# "prevalence of X (93.6% vs. 83.8%, P < 0.001, SMD = 0.312)". Applied only to an "SMD"/"standardized difference"
# written WITHOUT an interval (every effect SMD in the gold carries one) and never to Cohen's d / Hedges' g.
BALANCE_CONTEXT = re.compile(
    r"\d+(?:\.\d+)?\s*%?\s*(?:vs\.?|versus)\s*\d+(?:\.\d+)?\s*%"  # a proportion contrast just before it
    r"|\b(?:prevalence|baseline|covariates?|propensity|inverse[- ]probability|IPTW|weighting|weighted|matched|"
    r"matching|balance[d]?|imbalance|standardi[sz]ed\s+differences?)\b",
    re.I,
)
# "HR 72 beats/min (95% CI 70-74)" and "mean RR interval was 850 ms" are heart rates / ECG intervals, not ratios
HEART_CONTEXT = re.compile(r"heart[- ]rate|pulse|\bbeats?\b|\bbpm\b|\bR-R\b|\bRR[- ]interval", re.I)
RR_INTERVAL_AFTER = re.compile(r"\s+intervals?\b", re.I)
# a pathological "sentence" (a flattened table, a file with no punctuation) must not make the regexes quadratic;
# the longest real sentence in the 166 corpus papers is 3,965 characters
MAX_SENTENCE_CHARS = 6000
P_BEFORE_VALUE = re.compile(r"(?<![A-Za-z])[pP]\s*(?:<=|>=|[<>=≤≥])\s*$")
N_EQ_RE = re.compile(r"(?<![A-Za-z])[nN]\s*=\s*(?P<n>\d{1,3}(?:,\d{3})+|\d+)\b")

# Wording that marks an effect size as planned/hypothetical rather than observed. Positional on purpose:
# a stray "or less" elsewhere in the sentence must not veto a real result.
PLAN_BEFORE_RE = re.compile(
    r"(?:\bpower(?:ed)?\s+(?:to|of)\b|\bpowered\b|\bto detect\b|\ba priori\b|\bassum(?:e|ed|ing|ption)\w*|"
    r"\banticipat\w*|\bexpected\b|\baimed?\b|\bhypothes[ie]s\w*|\bthreshold\b|\bMCID\b|"
    r"\bminimal clinically|\bset at\b|\btarget\w*)[^.;]{0,70}$",
    re.I,
)
PLAN_AFTER_RE = re.compile(
    r"^\W{0,3}(?:\w+\s+){0,2}?(?:or more|or greater|or less|or higher|at least|set a priori|a priori|"
    r"was assumed|was expected|clinically (?:important|meaningful|relevant))",
    re.I,
)

_P_OPS = {"≤": "<=", "≥": ">="}


@dataclass(frozen=True)
class EffectCandidate:
    metric: Metric
    value: float
    ci_low: float | None
    ci_high: float | None
    ci_level: float | None
    unit: str | None
    p_value: float | None
    p_operator: str | None
    n: int | None
    start: int  # absolute offsets of the effect expression
    end: int


def _p_value(m: re.Match[str]) -> float:
    if m["ten"]:
        return 10.0 ** -int(m["texp"])  # "P < 10-4" means 1e-4
    value = float(m["val"].replace("\u2212", "-"))
    if m["exp"]:
        value *= 10 ** -int(m["exp"])  # an unsigned exponent is read as negative: nobody reports p = 1e+6
    return value


def parse_number(s: str) -> float:
    return float(re.sub(r"[\s£$€]", "", s).replace("\u2212", "-").replace("\u2013", "-"))


def _tail(sentence: str, pos: int, *, tight: bool = False) -> re.Match[str] | None:
    forms = (TAIL_LABELLED_TIGHT, TAIL_BARE) if tight else (TAIL_LABELLED, TAIL_BARE, TAIL_COMMA)
    for rx in forms:
        m = rx.match(sentence, pos)
        if m:
            return m
    return None


def _group_window(s: str, start: int, end: int) -> tuple[int, int]:
    """Span of the bracketed group an estimate sits in (or opens right after it), for n lookup."""
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
            if depth < 0:
                return start, i  # estimate is inside a group; this closes it
            if depth == 0 and i >= end:
                return start, i  # estimate was top-level; this closes the group that follows it
    return start, len(s)


def _interval(m: re.Match[str] | None) -> tuple[float | None, float | None, float | None]:
    if m is None:
        return None, None, None
    gd = m.groupdict()
    level = gd.get("level") or gd.get("level2")
    return parse_number(gd["lo"]), parse_number(gd["hi"]), float(level) if level else None


def find_effect_candidates(sentence: str, offset: int = 0) -> list[EffectCandidate]:
    """All effect estimates in ``sentence``; offsets are shifted by ``offset``."""
    raw: list[dict] = []  # intermediate candidates: metric, value, lo, hi, level, unit, start, end
    if len(sentence) > MAX_SENTENCE_CHARS:
        return []
    for m in HEAD_RE.finditer(sentence):
        if P_BEFORE_VALUE.search(sentence[max(0, m.start("value") - 8) : m.start("value")]):
            continue  # "... p = 0.032": a p-value is never the estimate
        if DOI_AFTER.match(sentence, m.end("value")):
            continue
        window = sentence[max(0, m.start() - 160) : m.start()]
        if WITHIN_ARM_RE.search(window) and "between" not in window.lower():
            continue  # "Within the experimental group ... (MD = -2.75, 95% CI ...)": a change, not a contrast
        metric = next(Metric[k[2:]] for k, v in m.groupdict().items() if k.startswith("m_") and v)
        value = parse_number(m["value"])
        name = m.group(f"m_{metric.name}")
        if SD_LABEL_AFTER.match(sentence, m.end(f"m_{metric.name}")):
            continue  # "mean difference (SD) of X was -0.23 (9.1)": a mean change with its SD, not an estimate with an interval
        if metric is Metric.RR and RR_INTERVAL_AFTER.match(sentence, m.end(f"m_{metric.name}")):
            continue  # "RR interval 850 ms"
        if (metric in (Metric.HR, Metric.RR) and len(name) <= 5 and value >= 20
                and HEART_CONTEXT.search(sentence[max(0, m.start() - 60) : m.end("value") + 40])):
            continue  # abbreviation HR/RR with a heart-rate context and an implausible ratio
        unit_ws = re.sub(r"\s+", "", m["unit_ws"]) if m["unit_ws"] else None
        pos = m.end()

        tail = _tail(sentence, pos)
        unit = unit_ws
        if tail is None:  # maybe an unlisted/longer unit ("ml/kg/min") sits between value and interval
            gm = UNIT_GEN_RE.match(sentence, m.end("value"))
            if gm and (t2 := _tail(sentence, gm.end())):
                tail, unit, unit_ws = t2, gm["u"], None
        if (m.group("fn") or m.group("fn2")) and tail is None:
            continue  # a bare number after a long filler ("... were observed from 6 months") is too weak
        if (metric is Metric.SMD and tail is None and re.search(r"SMD|standardi", name, re.I)
                and BALANCE_CONTEXT.search(sentence[max(0, m.start() - 120) : m.end("value") + 20])):
            continue  # covariate-balance diagnostic, not an effect
        lo, hi, level = _interval(tail)
        end = tail.end() if tail else m.end()
        raw.append(dict(metric=metric, value=value, lo=lo, hi=hi, level=level, unit=unit,
                        known=unit_ws is not None, start=m.start(), end=end, tail=tail is not None))

        # continuation list: "... 0.75 (0.59-0.95), 0.68 (0.54-0.85) ..." reuses the metric
        cursor, count = end, 0
        while tail is not None and count < 10:
            skip = SKIP_AFTER_TAIL.match(sentence, cursor)
            cm = CONT_RE.match(sentence, skip.end() if skip else cursor)
            ct = _tail(sentence, cm.end(), tight=True) if cm else None
            if not (cm and ct):
                break
            clo, chi, clevel = _interval(ct)
            cu = re.sub(r"\s+", "", cm["unit_ws"]) if cm["unit_ws"] else unit_ws
            raw.append(dict(metric=metric, value=parse_number(cm["value"]), lo=clo, hi=chi,
                            level=clevel, unit=cu, known=cu is not None, start=cm.start("value"),
                            end=ct.end(), tail=True))
            cursor, count = ct.end(), count + 1

    raw.sort(key=lambda r: r["start"])
    p_matches = [
        pm for pm in P_RE.finditer(sentence)
        if not _P_NOT_EFFECT_AFTER.match(sentence, pm.end())
        and not _P_NOT_EFFECT_BEFORE.search(sentence[max(0, pm.start() - 40) : pm.start()])
    ]

    out: list[EffectCandidate] = []
    for i, r in enumerate(raw):
        metric, value, lo, hi = r["metric"], r["value"], r["lo"], r["hi"]
        # ---- sanity checks: a malformed or implausible reading is dropped, never "repaired"
        if metric.is_ratio and (value <= 0 or r["known"]):  # "hazard ratio ... was 118 mmHg"
            continue
        if lo is not None and hi is not None:
            if lo > hi or not (lo - 1e-9 <= value <= hi + 1e-9):
                lo = hi = None  # source typo / not this estimate's interval
        limit = raw[i + 1]["start"] if i + 1 < len(raw) else len(sentence)
        p = next((pm for pm in p_matches if r["start"] <= pm.start() < limit), None)
        if lo is None and p is None and (
            PLAN_BEFORE_RE.search(sentence[max(0, r["start"] - 80) : r["start"]])
            or PLAN_AFTER_RE.match(sentence[r["end"] : r["end"] + 60])
        ):
            continue  # "80% power to detect a HR of 0.80", "difference of 1 point or more"
        w0, w1 = _group_window(sentence, r["start"], r["end"])
        n_match = N_EQ_RE.search(sentence, w0, w1)
        out.append(
            EffectCandidate(
                metric=metric,
                value=value,
                ci_low=lo,
                ci_high=hi,
                ci_level=r["level"] if lo is not None else None,
                unit=r["unit"] if (r["unit"] and (r["tail"] or r["known"])) else None,
                p_value=_p_value(p) if p else None,
                p_operator=_P_OPS.get(p["op"], p["op"]) if p else None,
                n=int(n_match["n"].replace(",", "")) if n_match else None,
                start=offset + r["start"],
                end=offset + r["end"],
            )
        )
    return out
