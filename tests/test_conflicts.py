from evidencetrace.config import ConflictConfig
from evidencetrace.schemas import ConflictKind, Metric
from evidencetrace.verification import comparable, detect_conflicts
from helpers import make_finding

HR = Metric.HR


def kinds(findings, cfg=None):
    return [c.kind for c in detect_conflicts(findings, cfg)]


def test_direction_conflict_on_ratio_metric():
    a = make_finding(doc_id="a", metric=HR, value=0.78, ci=(0.65, 0.93), outcome="hospitalization")
    b = make_finding(doc_id="b", metric=HR, value=1.12, ci=(1.01, 1.24), outcome="hospitalization")
    (c,) = detect_conflicts([a, b])
    assert c.kind is ConflictKind.DIRECTION and c.severity == "high"
    assert "opposite directions" in c.explanation


def test_ratio_scale_is_symmetric_on_log_scale():
    a = make_finding(doc_id="a", metric=HR, value=0.5, ci=(0.4, 0.6))
    b = make_finding(doc_id="b", metric=HR, value=2.0, ci=(1.8, 2.2))
    assert kinds([a, b]) == [ConflictKind.DIRECTION]


def test_magnitude_conflict_same_direction_disjoint_cis():
    a = make_finding(doc_id="a", value=-8.2, ci=(-10.1, -6.3))
    b = make_finding(doc_id="b", value=-2.1, ci=(-5.0, 0.8))
    assert kinds([a, b]) == [ConflictKind.MAGNITUDE]


def test_significance_conflict_overlapping_cis():
    a = make_finding(doc_id="a", value=-6.0, ci=(-9.0, -3.0))
    b = make_finding(doc_id="b", value=-2.1, ci=(-5.0, 0.8))
    assert kinds([a, b]) == [ConflictKind.SIGNIFICANCE]


def test_consistent_results_do_not_conflict():
    a = make_finding(doc_id="a", value=-8.2, ci=(-10.1, -6.3))
    b = make_finding(doc_id="b", value=-6.0, ci=(-9.0, -3.0))
    assert kinds([a, b]) == []


def test_same_paper_never_conflicts_with_itself():
    a = make_finding(doc_id="a", value=-8.0, ci=(-10, -6), start=0)
    b = make_finding(doc_id="a", value=-1.0, ci=(-2, -0.5), start=500)
    assert kinds([a, b]) == []


def test_different_outcome_or_intervention_is_not_comparable():
    base = make_finding(doc_id="a", value=-8.0, ci=(-10, -6))
    other_outcome = make_finding(doc_id="b", value=2.0, ci=(1, 3), outcome="LDL cholesterol")
    other_drug = make_finding(doc_id="c", value=2.0, ci=(1, 3), intervention="Drug Omega")
    assert kinds([base, other_outcome, other_drug]) == []


def test_missing_intervention_is_not_a_wildcard_by_default():
    a = make_finding(doc_id="a", value=-8.0, ci=(-10, -6))
    b = make_finding(doc_id="b", value=2.0, ci=(1, 3), intervention=None)
    assert not comparable(a, b, ConflictConfig())
    assert comparable(a, b, ConflictConfig(require_intervention_and_outcome=False))


def test_p_value_only_significance():
    a = make_finding(doc_id="a", value=-6.0, ci=None, p=0.001, p_op="<")
    b = make_finding(doc_id="b", value=-5.0, ci=None, p=0.4, p_op="=")
    assert kinds([a, b]) == [ConflictKind.SIGNIFICANCE]


def test_nonpositive_ratio_is_skipped_not_crashed():
    a = make_finding(doc_id="a", metric=HR, value=0.0, ci=(0.0, 0.5))
    b = make_finding(doc_id="b", metric=HR, value=1.2, ci=(1.1, 1.3))
    assert kinds([a, b]) == []


def test_population_difference_is_flagged_in_the_explanation():
    a = make_finding(doc_id="a", metric=HR, value=0.78, ci=(0.65, 0.93), population="adults with hypertension")
    b = make_finding(doc_id="b", metric=HR, value=1.12, ci=(1.01, 1.24), population="children with asthma")
    (c,) = detect_conflicts([a, b])
    assert "Populations differ" in c.explanation
