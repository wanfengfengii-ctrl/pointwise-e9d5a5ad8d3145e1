from publication.store import PublicationStore, SignedReport
from review.compatibility import match_parents
from review.intake import IntakeStore
from review.results import ReviewResult, report_body


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
