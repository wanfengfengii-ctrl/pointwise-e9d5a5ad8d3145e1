from evidence.relations import intersect_relations
from review.compatibility import match_parents
from review.contrast import evaluate_contrast, supports_claim
from review.intake import IntakeStore
from review.results import CaseFinding, ReviewResult, build_result, parse_pair


def assess(store: IntakeStore, a_key: str, b_key: str, contrast, claim) -> ReviewResult:
    coefficients = parse_pair(contrast, 'contrast')
    claimed_pair = parse_pair(claim, 'claim')
    parents = match_parents(store, a_key, b_key)
    right_cases = dict(parents.b.piece.cases)
    findings = []
    for excluded, left in parents.a.piece.cases:
        common = intersect_relations(left, right_cases[excluded])
        if common.consistent:
            findings.append(CaseFinding(excluded, evaluate_contrast(common, coefficients),
                                        supports_claim(common, claimed_pair)))
    return build_result(parents.run_id, parents.ids, parents.checksums, coefficients, claimed_pair, findings)
