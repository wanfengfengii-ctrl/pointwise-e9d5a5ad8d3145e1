from fractions import Fraction

from evidence.drift import parse_interval
from evidence.polyhedra import contrast_range
from observations.rationals import format_rational
from publication.store import PublicationStore, SignedReport
from review.compatibility import match_drift_parents, match_parents
from review.intake import IntakeStore
from review.results import ReviewResult, parse_pair, report_body


def sign(store: PublicationStore, intake: IntakeStore, result: ReviewResult, *, after_body=None) -> SignedReport:
    body = report_body(result)
    if not isinstance(result.parents, tuple) or len(result.parents) != 2:
        raise ValueError('a review result requires two parent keys')
    parents = match_parents(intake, *result.parents)
    if (result.run_id, result.parent_checksums) != (parents.run_id, parents.checksums):
        raise ValueError('the review result does not match the received parent evidence')

    # The findings must form an ordered subsequence of the complete case list.
    findings = iter(case['excluded_batch'] for case in body['cases'])
    end = object()
    expected = next(findings, end)
    for excluded in parents.case_ids:
        if excluded == expected:
            expected = next(findings, end)
    if expected is not end:
        raise ValueError('review cases do not match the parents and their fixed order')
    return store.commit_report(body, parents.ids, parents.checksums, after_body=after_body)


def sign_drift(store: PublicationStore, intake: IntakeStore, a_key: str, b_key: str,
               window, contrast, *, after_body=None) -> SignedReport:
    """Sign a drift report from the designated A and B received drift pieces."""
    coefficients = parse_pair(contrast, 'contrast')
    window = parse_interval(window, 'window')
    parents = match_drift_parents(intake, a_key, b_key)
    z_low, z_high = parents.work_box[2]
    if not z_low <= window[0] or not window[1] <= z_high:
        raise ValueError('the window must lie within the work box z domain')
    right_cases = dict(parents.b.piece.cases)
    cases = []
    for excluded, left in parents.a.piece.cases:
        right = right_cases[excluded]
        if left.empty or right.empty:
            continue
        equalities = left.equalities + right.equalities
        inequalities = left.inequalities + right.inequalities + (
            (Fraction(0), Fraction(0), Fraction(1), window[1]),
            (Fraction(0), Fraction(0), Fraction(-1), -window[0]),
        )
        outcome = contrast_range(equalities, inequalities, coefficients)
        if outcome is None:
            continue
        low, high = outcome
        cases.append({'excluded_batch': excluded,
                      'range': [format_rational(low), format_rational(high)]})
    body = {
        'kind': 'drift',
        'run_id': parents.run_id,
        'parents': list(parents.ids),
        'parent_checksums': list(parents.checksums),
        'work_box': {axis: [format_rational(low), format_rational(high)]
                     for axis, (low, high) in zip(('x', 'y', 'z'), parents.work_box)},
        'window': [format_rational(window[0]), format_rational(window[1])],
        'contrast': [format_rational(value) for value in coefficients],
        'cases': cases,
    }
    return store.commit_report(body, parents.ids, parents.checksums, after_body=after_body)
