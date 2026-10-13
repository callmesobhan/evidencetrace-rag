import pytest

from evidencetrace.extraction.candidates import find_effect_candidates
from evidencetrace.extraction.extractor import detect_attribution, extract_findings
from evidencetrace.extraction.fields import RuleFieldTagger
from evidencetrace.ingest import Document, parse_file
from evidencetrace.schemas import Attribution, Metric


@pytest.mark.parametrize(
    "sentence, metric, value, ci, p",
    [
        ("HR 0.78 (95% CI 0.65–0.93; p=0.006)", Metric.HR, 0.78, (0.65, 0.93), 0.006),
        ("hazard ratio, 0.78; 95% CI, 0.65 to 0.93", Metric.HR, 0.78, (0.65, 0.93), None),
        ("The odds ratio was 1.5 (95% CI: 1.1-2.0, P < .001)", Metric.OR, 1.5, (1.1, 2.0), 0.001),
        ("mean difference −8.2 mmHg, 95% CI −10.1 to −6.3", Metric.MD, -8.2, (-10.1, -6.3), None),
        ("risk ratio of 0.9 [95% CI 0.8, 1.0]", Metric.RR, 0.9, (0.8, 1.0), None),
        ("SMD = -0.35 (95%CI -0.6 to -0.1)", Metric.SMD, -0.35, (-0.6, -0.1), None),
        ("The hazard ratio for death was 0.8 (95% CI 0.7 to 0.9)", Metric.HR, 0.8, (0.7, 0.9), None),
    ],
)
def test_effect_formats(sentence, metric, value, ci, p):
    (c,) = find_effect_candidates(sentence)
    assert c.metric is metric and c.value == value
    assert (c.ci_low, c.ci_high) == ci
    assert c.p_value == p
    assert c.ci_level in (95.0,)


def test_lowercase_or_is_not_an_odds_ratio():
    assert find_effect_candidates("Treatment or 0.5 mg placebo was given (95% CI 1 to 2).") == []


def test_estimate_without_ci_is_still_a_candidate():
    (c,) = find_effect_candidates("The hazard ratio was 0.7 (p=0.01).")
    assert c.ci_low is None and c.p_value == 0.01


def test_two_estimates_get_their_own_p_values():
    cs = find_effect_candidates("HR 0.7 (95% CI 0.5 to 0.9; p=0.01) and OR 1.4 (95% CI 1.1 to 1.8; p=0.002)")
    assert [(c.metric, c.p_value) for c in cs] == [(Metric.HR, 0.01), (Metric.OR, 0.002)]


def test_n_only_when_stated_alongside_the_estimate():
    (a,) = find_effect_candidates("HR 0.7 (95% CI 0.5 to 0.9; n = 1,234)")
    assert a.n == 1234
    # group sizes and event counts are not the analysis N
    (b,) = find_effect_candidates("Among 412 patients, HR 0.7 (95% CI 0.5 to 0.9)")
    (c,) = find_effect_candidates("fewer hospitalised (n = 111; 20%) than usual care (HR 0.76, 95% CI 0.49-0.98, p = 0.032)")
    assert b.n is None and c.n is None


def test_rule_tagger_svo_and_negation():
    f = RuleFieldTagger().tag(
        "Drug Zeta did not significantly reduce systolic blood pressure compared with placebo "
        "(mean difference −2.1 mmHg)."
    )
    assert (f.intervention, f.outcome, f.comparator) == (
        "Drug Zeta", "systolic blood pressure", "placebo",
    )
    assert f.confidence == 1.0


def test_rule_tagger_population():
    f = RuleFieldTagger().tag(
        "Drug Zeta increased hospitalization compared with placebo in patients with heart failure "
        "(hazard ratio 1.12, 95% CI 1.01 to 1.24)."
    )
    assert f.population == "patients with heart failure"


def test_rule_tagger_gives_up_gracefully():
    f = RuleFieldTagger().tag("A previous trial by Hartmann et al. [3] reported HR 0.55.")
    assert f.intervention is None and f.confidence == 0.0


def test_attribution_heuristics():
    assert detect_attribution("Smith et al. found HR 0.5.", "results") is Attribution.CITED
    assert detect_attribution("Prior work [4] found HR 0.5.", "results") is Attribution.CITED
    assert detect_attribution("We found HR 0.5.", "introduction") is Attribution.CITED
    assert detect_attribution("We found HR 0.5.", "results") is Attribution.OWN


def test_sample_extraction(samples):
    a = extract_findings(parse_file(samples / "papers" / "paper_a.txt"))
    # abstract copy of the SBP result is deduplicated against the Results copy
    assert len(a) == 2
    assert {f.span.section for f in a} == {"results"}

    b = extract_findings(parse_file(samples / "papers" / "paper_b.txt"))
    cited = [f for f in b if f.attribution is Attribution.CITED]
    assert len(cited) == 1 and cited[0].value == 0.55
    assert cited[0].confidence < 0.5  # cited + untaggable => low confidence


def test_finding_offsets_index_the_canonical_text(samples):
    doc = parse_file(samples / "papers" / "paper_c.txt")
    for f in extract_findings(doc):
        assert doc.text[f.span.start : f.span.end] == f.span.text
        assert f.doc_sha256 == doc.sha256


def test_extractor_on_text_without_results_returns_nothing():
    doc = Document.from_text("d", "Title\n\nResults\n\nEffects on stroke are shown in Figure 3.")
    assert extract_findings(doc) == []


# --------------------------------------------------------------------------------------------
# Regression tests for failure classes found auditing 355 real predictions (M1 dev split).
# Sentences are paraphrased shapes of the real ones, not copies.
# --------------------------------------------------------------------------------------------
def one(sentence):
    (c,) = find_effect_candidates(sentence)
    return c


@pytest.mark.parametrize(
    "sentence, value, ci, level",
    [
        ("mean difference of 0.9, 95% CI [0.1, 1.6]; p = 0.032", 0.9, (0.1, 1.6), 95.0),
        ("mean difference of −0.3 [−0.5, −0.1], p = 0.003", -0.3, (-0.5, -0.1), None),
        ("HR 0.82 (0.62–1.10; P=0.01)", 0.82, (0.62, 1.10), None),
        ("hazard ratio, 0.57; 95% CI, 0.47-0.68; P < .001", 0.57, (0.47, 0.68), 95.0),
        ("mean difference: 5.1%; 95% confidence interval [CI] 3.1–7.1%, p < 0.001", 5.1, (3.1, 7.1), 95.0),
        ("mean difference of -1.96 (95% confidence interval (CI): -3.68 to -0.24, p = 0.026)", -1.96, (-3.68, -0.24), 95.0),
        ("(HR = 0.538, CIs 0.316-0.915, n = 674, P = 0.022)", 0.538, (0.316, 0.915), None),
        ("(aOR 0.73, 95% 0.62–0.87)", 0.73, (0.62, 0.87), 95.0),
        ("rate ratio [RR] 0.52, 95% CI 0.39–0.91, p = 0.017", 0.52, (0.39, 0.91), 95.0),
        ("(SMD -0.12, − 0.21 to − 0.03)", -0.12, (-0.21, -0.03), None),
        ("(OR: 1.13; 95% CI: .82, 1.55)", 1.13, (0.82, 1.55), 95.0),
        ("(sub-HR=1.55 (1.14,2.09))", 1.55, (1.14, 2.09), None),
        ("risk difference of 12.2% (95% CI −1.7% to 26.1%)", 12.2, (-1.7, 26.1), 95.0),
        ("(RR 2.48, 1.36–4.52, I2 = 65%)", 2.48, (1.36, 4.52), None),
        ("mean difference −21.83 mmol/L [CI, −58.99 to 39.19]; P>0.99", -21.83, (-58.99, 39.19), None),
    ],
)
def test_interval_notations_seen_in_real_papers(sentence, value, ci, level):
    c = one(sentence)
    assert c.value == value and (c.ci_low, c.ci_high) == ci and c.ci_level == level


@pytest.mark.parametrize(
    "sentence, unit",
    [
        ("(MD: 27.23 m; 95% CI: 8.28–46.18; P = .005)", "m"),
        ("(MD: −90.27 dynes·s·cm−5; 95% CI: −119.30 to −61.23)", "dynes·s·cm−5"),
        ("mean difference 312 mL [95% CI, 26–598]", "mL"),
        ("adjusted mean difference 1.45 cm/s compared to beta-blockers (95% CI 1.22–1.73; p = 0.002)", "cm/s"),
        ("mean difference −8.2 mmHg, 95% CI −10.1 to −6.3", "mmHg"),
    ],
)
def test_units_and_filler_between_value_and_interval(sentence, unit):
    c = one(sentence)
    assert c.unit == unit and c.ci_low is not None


def test_continuation_lists_reuse_the_metric():
    cs = find_effect_candidates(
        "The HR was 0.80 (95% CI, 0.66-0.97; P = .02) for MI, 0.71 (95% CI, 0.66-0.77; P < .001) for stroke, "
        "and 0.68 (95% CI, 0.54-0.85; P < .001) for HF."
    )
    assert [(c.metric, c.value, c.p_value) for c in cs] == [
        (Metric.HR, 0.80, 0.02), (Metric.HR, 0.71, 0.001), (Metric.HR, 0.68, 0.001),
    ]
    bare = find_effect_candidates(
        "adjusted hazard ratios were 0.87 (0.69–1.10; P=0.23), 0.75 (0.59–0.95; P=0.02), and 0.94 (0.74–1.20; P=0.64) for Q2 to Q4"
    )
    assert [c.value for c in bare] == [0.87, 0.75, 0.94] and [c.p_value for c in bare] == [0.23, 0.02, 0.64]


@pytest.mark.parametrize(
    "sentence",
    [
        "The treatment effect will be extracted as an adjusted mean difference, 95% CI and p value.",  # "95" is a level
        "OR: 1,8; IC 95%: 1,3 a 2,6; p <0,001",                       # decimal commas: refuse rather than misparse
        "the lowest hazard ratio in CBP was 118 mmHg",                # a ratio has no mmHg
        "to provide 80% power to detect a HR of 0.80 for this endpoint",
        "no adjusted mean difference of 1 point or more was observed",  # threshold, not a result
        "geometric mean difference 0.77; 95% CI 0.64-0.92",            # a ratio of geometric means, not an MD
    ],
)
def test_things_that_look_like_estimates_but_are_not(sentence):
    assert find_effect_candidates(sentence) == []


def test_interval_that_does_not_contain_its_own_estimate_is_dropped_not_repaired():
    c = one("(RR, 1.21; 95% CI, 085-1.73; P = .29)")  # source typo for 0.85-1.73
    assert c.value == 1.21 and c.ci_low is None and c.p_value == 0.29


def test_p_values_for_interaction_and_heterogeneity_are_not_the_estimates_p():
    a, b = find_effect_candidates(
        "(age <=72: HR, 0.84; 95% CI, 0.70-0.99; age >72: HR, 1.17; 95% CI, 0.92-1.50; P = .03 for interaction)"
    )
    assert a.p_value is None and b.p_value is None
    assert one("(RR 2.48, 1.36-4.52, I2 = 65%, Chi2 = 2.85, P = .09)").p_value is None


def test_canonical_text_turns_unicode_hyphens_into_ranges():
    from evidencetrace.ingest import Document

    doc = Document.from_text("d", "Results\n\nOR 0.73, 95% CI 0.31\u20101.69; P=.46")
    c = one(doc.text.splitlines()[-1])
    assert (c.ci_low, c.ci_high) == (0.31, 1.69)


def test_sentence_split_keeps_citation_markers_with_the_sentence_they_cite():
    from evidencetrace.ingest import Document, split_sentences

    doc = Document.from_text("d", "Results\n\nNo difference in KFRT.[11] Chlorthalidone raised risk (HR, 1.70; 95% CI, 1.55-1.87).")
    texts = [s.text for s in split_sentences(doc)]
    assert texts == ["No difference in KFRT.[11]", "Chlorthalidone raised risk (HR, 1.70; 95% CI, 1.55-1.87)."]


def test_clause_like_field_candidates_are_rejected():
    f = RuleFieldTagger().tag(
        "Time to new-onset AF was numerically reduced but formally not significantly different (HR 0.66)."
    )
    assert f.intervention is None and f.outcome is None


def test_methods_section_plans_are_not_findings():
    from evidencetrace.ingest import Document

    doc = Document.from_text(
        "d", "Methods\n\nWe propose to assess a mean difference of 0.15 in medication counts.\n\nResults\n\nMD 0.2 (95% CI 0.1 to 0.3)."
    )
    assert [f.value for f in extract_findings(doc)] == [0.2]


def test_planning_cues_are_positional_not_sentence_wide():
    # "or less" earlier in the sentence and "sample size" later must not veto a real, reported estimate
    assert one("In short trials (two years or less), the average effect was a 43% relative risk reduction (RR 0.57), but small.").value == 0.57
    assert one("The excess in bladder cancer was substantial (HR = 1.34) but not significant given the limited sample size.").value == 1.34
    # ... while genuine plans are still dropped
    assert find_effect_candidates("The relative risk of 0.68 set a priori for the coprimary outcome was excluded.") == []


def test_bare_restatement_of_an_estimate_is_dropped_when_an_interval_copy_exists():
    from evidencetrace.ingest import Document

    doc = Document.from_text(
        "d",
        "Results\n\nMD 0.25 (95% CI -0.01 to 0.51; p = 0.03).\n\nDiscussion\n\nOur mean difference of 0.25 is small.",
    )
    fs = extract_findings(doc)
    assert [(f.value, f.ci is not None) for f in fs] == [(0.25, True)]


@pytest.mark.parametrize(
    "sentence, metric, value, ci",
    [
        ("aRR 0.81, 95% CI 0.61 to 1.08; p = 0.149", Metric.RR, 0.81, (0.61, 1.08)),
        ("adjusted mean difference versus placebo in change from baseline in LVEF was 2.5% (95% CI: 1.00-4.06, P = 0.002)", Metric.MD, 2.5, (1.0, 4.06)),
        ("mean difference with dapagliflozin versus placebo - CRP < 1.07 mg/L: -1.12%; 95% CI: -2.83-0.58%, p = 0.188", Metric.MD, -1.12, (-2.83, 0.58)),
        ("adjusted mean difference vs. placebo: +9.3 [6.5; 12.1]", Metric.MD, 9.3, (6.5, 12.1)),
        ("The RR was calculated as 1.17 (95% CI, 0.84-1.62; P = .36)", Metric.RR, 1.17, (0.84, 1.62)),
        ("(MD with 95% CI -6.46 [-8.23, -4.69], moderate certainty)", Metric.MD, -6.46, (-8.23, -4.69)),
        ("The mean between treatment group difference over time was 7.3 g/L (95% CI 6.2, 8.5; P < .001)", Metric.MD, 7.3, (6.2, 8.5)),
        ("absolute risk reduction at Week 156 was -0.02 (95% CI -0.04 to -0.002; P = .035)", Metric.RD, -0.02, (-0.04, -0.002)),
    ],
)
def test_recall_gaps_found_by_the_near_miss_audit(sentence, metric, value, ci):
    c = one(sentence)
    assert (c.metric, c.value, (c.ci_low, c.ci_high)) == (metric, value, ci)


def test_discussion_numbers_are_the_authors_only_if_the_sentence_says_so():
    from evidencetrace.extraction.extractor import detect_attribution
    from evidencetrace.schemas import Attribution

    other = "In a study combining three cohorts, stage B had a 10-fold risk (HR 10.6, 95% CI 9.0-12.5)."
    ours = "In our study, stage B had a 10-fold risk (HR 10.6, 95% CI 9.0-12.5)."
    assert detect_attribution(other, "discussion") is Attribution.CITED
    assert detect_attribution(ours, "discussion") is Attribution.OWN
    assert detect_attribution(other, "results") is Attribution.OWN  # Results is the paper's own by default


def test_label_letter_is_not_an_initial():
    from evidencetrace.ingest import Document, split_sentences

    doc = Document.from_text("d", "Discussion\n\nRisk exceeded that of HF stage A. Therefore our results are conservative. Hartmann J. Smith et al. agreed.")
    texts = [s.text for s in split_sentences(doc)]
    assert texts[0] == "Risk exceeded that of HF stage A." and texts[1].startswith("Therefore")


@pytest.mark.parametrize(
    "sentence, metric, value, ci",
    [
        ("(AOR = 159.32, [95% CI: 124.53, 203.81; P < 0.001])", Metric.OR, 159.32, (124.53, 203.81)),
        ("a pooled mean difference in 6MWD of 27.23 meters (95% CI: 8.28 to 46.18; P = .005)", Metric.MD, 27.23, (8.28, 46.18)),
        ("(RR 0.97,0.81 to 1.16) [[21]]", Metric.RR, 0.97, (0.81, 1.16)),
        ("hazard ratio (HR) for COPD vs. no COPD 1.4 (95% CI 1.2-1.6)", Metric.HR, 1.4, (1.2, 1.6)),
        ("The mean difference SBP was - 4.41 mmHg (95% CI, - 5.52to - 3.30)", Metric.MD, -4.41, (-5.52, -3.30)),
        ("(mean difference \u00a3\u2212407.80, 95% CI \u2212793.47 to +39.55; p = 0.054)", Metric.MD, -407.80, (-793.47, 39.55)),
        ("treatment group difference in baseline-adjusted mean CCA-IMT at 24 months was -0.003 mm (95% CI -0.022 to 0.015, p = 0.718)", Metric.MD, -0.003, (-0.022, 0.015)),
        ("absolute risk reduction (semaglutide 1.0 mg - placebo) at Week 156 for CV death was -0.02 (95% CI -0.04 to -0.002; P = .035)", Metric.RD, -0.02, (-0.04, -0.002)),
        ("(SHR, 0.89; 95% CI 0.80-0.99)", Metric.HR, 0.89, (0.8, 0.99)),
        ("(AMD = -2.020 kg/m2, 95% CI: -3.229 to -0.812, p = 0.001)", Metric.MD, -2.02, (-3.229, -0.812)),
        ("adjusted mean difference for LVEF 2.3% (95% confidence interval [CI] 0.3-4.2; p = 0.021)", Metric.MD, 2.3, (0.3, 4.2)),
    ],
)
def test_second_round_recall_fixes(sentence, metric, value, ci):
    cs = find_effect_candidates(sentence)
    assert cs, sentence
    c = cs[0]
    assert (c.metric, c.value, (c.ci_low, c.ci_high)) == (metric, value, ci)


def test_wmd_with_bracketed_ci_label_and_continuation():
    cs = find_effect_candidates("(WMD [95% CI]: -4.1 mm Hg [-6.0, -2.2] and -3.7 mm Hg [-4.6, -2.8], respectively)")
    assert [(c.metric, c.value, c.unit) for c in cs] == [(Metric.MD, -4.1, "mmHg"), (Metric.MD, -3.7, "mmHg")]


def test_arr_is_not_read_as_a_risk_ratio():
    assert find_effect_candidates("ARR 0.05 (95% CI 0.01 to 0.09)") == []  # absolute risk reduction abbreviation


@pytest.mark.parametrize(
    "sentence",
    [
        "Sustained between-group differences in both systolic and diastolic BP in older patients were observed from 6 months on (Figure 1).",
        "The mean difference in SBP at 3 months (change = -13.8 mm Hg in intervention arm) was not significant.",
        "The risk differences in the proportion of patients achieving an increase of more than 5, 10, and 15 points were reported.",
    ],
)
def test_a_bare_number_after_a_long_phrase_is_not_an_estimate(sentence):
    assert find_effect_candidates(sentence) == []


def test_metric_name_is_not_stolen_by_a_nearby_word_group():
    c = one("higher in the device group with a risk difference of 12.2% (95% CI -1.7% to 26.1%)")
    assert c.metric is Metric.RD and c.value == 12.2


def test_long_units_and_comma_fillers():
    assert one("a mean difference of +2.03 ml/kg/min (95% CI -0.06 to 4.12; p = 0.056)").ci_high == 4.12
    c = one("absolute risk reduction (semaglutide 1.0 mg - placebo) at Week 156 for CV death, MI, or stroke was -0.02 (95% CI -0.04 to -0.002; P = .035)")
    assert (c.metric, c.value, c.ci_low) == (Metric.RD, -0.02, -0.04)


def test_abbreviations_are_expanded_from_the_papers_own_definitions():
    from evidencetrace.abbreviations import aliases_for, find_abbreviations

    text = ("Global longitudinal strain (GLS) and the mean pulmonary artery pressure (mPAP) were measured; "
            "hospitalization for heart failure (HHF) was a secondary outcome (95% CI).")
    abbr = find_abbreviations(text)
    assert abbr["GLS"] == "Global longitudinal strain" and abbr["mPAP"] == "mean pulmonary artery pressure"
    assert "95% CI" not in abbr and "CI" not in abbr  # not definitions
    assert aliases_for("improvement in GLS was 1.3", abbr) == ["Global longitudinal strain"]
    assert aliases_for("the mean pulmonary artery pressure fell", abbr) == ["mPAP"]


def test_hyphenated_compounds_match_their_parts():
    from evidencetrace.textnorm import tokenize

    assert {"semaglutid", "treat"} <= set(tokenize("semaglutide-treated patients"))
    assert "semaglutid" in tokenize("effect of semaglutide")


def test_scientific_notation_p_values():
    cs = find_effect_candidates("(OR = 0.46; 95% CI, 0.34-0.63; p = 1.02 \u00d7 10\u22126), HF (OR = 0.62; 95% CI, 0.49-0.79; p = 0.0001)")
    assert [c.p_value for c in cs] == [pytest.approx(1.02e-6), 0.0001]


# --- gaps found by INDEPENDENT annotators on papers the developer had never seen -----------------------
@pytest.mark.parametrize(
    "sentence, metric, value, ci",
    [
        ("(mean OR, 0.58; 95% CrI, 0.35-0.89)", Metric.OR, 0.58, (0.35, 0.89)),
        ("the mean difference was 0.33 (95% credible interval, -1.37 to 2.03) days", Metric.MD, 0.33, (-1.37, 2.03)),
        ("(LSMD, -2.5; 95% CI, -3.8 to -1.2; P < .001)", Metric.MD, -2.5, (-3.8, -1.2)),
        ("Cohen d, -1.1 [95% CI, -2.5 to 0.3]", Metric.SMD, -1.1, (-2.5, 0.3)),
        ("the mean difference at week 52, -2.91; 95% CI, -5.87 to 0.05", Metric.MD, -2.91, (-5.87, 0.05)),
        ("absolute difference in risk, 8.9; 97.5% CI, -5.0 to 22.7", Metric.RD, 8.9, (-5.0, 22.7)),
    ],
)
def test_independent_annotator_findings(sentence, metric, value, ci):
    cs = find_effect_candidates(sentence)
    assert cs, sentence
    c = cs[0]
    assert (c.metric, c.value) == (metric, value)
    if ci is not None:
        assert (c.ci_low, c.ci_high) == ci


def test_a_doi_is_not_a_risk_ratio_and_a_within_arm_change_is_not_a_contrast():
    assert find_effect_candidates("see trial registration RR2-10.1186/s13063-022-06728-5 for details") == []
    assert find_effect_candidates(
        "Within the experimental group, systolic pressure fell (MD = -2.75 mmHg, 95% CI = -7.73, 2.22, p = 0.005)"
    ) == []
    # ... but a contrast that merely mentions the group still counts
    assert find_effect_candidates(
        "Between-group, relative to the experimental group, systolic pressure fell (MD = -2.75 mmHg, 95% CI = -7.73, -1.2)"
    )


@pytest.mark.parametrize("dash", ["\u2013", "\u2212", "-"])
def test_a_minus_sign_is_never_swallowed_as_filler(dash):
    """Regression: 'difference of \u2013 3.35g/m2' once came back as +3.35 (and the CI was then dropped as
    inconsistent). A provenance check cannot catch this: the digits are in the text, only the sign is wrong."""
    sentence = f"an adjusted mean difference of {dash} 3.35g/m2 (95% CI {dash} 5.9 to {dash} 0.81 g/m2, p = 0.01)"
    (c,) = find_effect_candidates(sentence)
    assert c.value == -3.35 and (c.ci_low, c.ci_high) == (-5.9, -0.81) and c.unit == "g/m2"
