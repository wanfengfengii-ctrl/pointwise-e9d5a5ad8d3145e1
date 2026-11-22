from dataclasses import dataclass
from fractions import Fraction

from observations.rationals import format_rational, parse_rational
from review.contrast import ContrastRange


@dataclass(frozen=True, slots=True)
class CaseFinding:
    excluded_batch: str | None
    contrast: ContrastRange
    supports_claim: bool


@dataclass(frozen=True, slots=True)
class ReviewResult:
    run_id: str
    parents: tuple[str, str]
    parent_checksums: tuple[str, str]
    contrast: tuple[Fraction, Fraction]
    claim: tuple[Fraction, Fraction]
    findings: tuple[CaseFinding, ...]

    @property
    def supporting_cases(self) -> tuple[str | None, ...]:
        return tuple(finding.excluded_batch for finding in self.findings if finding.supports_claim)

    @property
    def supported(self) -> bool:
        return bool(self.supporting_cases)


def parse_pair(values, label: str) -> tuple[Fraction, Fraction]:
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        raise ValueError(f'{label} requires two rational values')
    try:
        return parse_rational(values[0]), parse_rational(values[1])
    except ValueError as error:
        raise ValueError(f'invalid {label}: {error}') from error


def build_result(run_id: str, parents: tuple[str, str], parent_checksums: tuple[str, str],
                 contrast: tuple[Fraction, Fraction], claim: tuple[Fraction, Fraction],
                 findings) -> ReviewResult:
    return ReviewResult(run_id, parents, parent_checksums, contrast, claim, tuple(findings))


def _case_body(finding: CaseFinding) -> dict:
    if not isinstance(finding, CaseFinding) or not isinstance(finding.contrast, ContrastRange):
        raise ValueError('invalid case finding')
    if type(finding.supports_claim) is not bool:
        raise ValueError('a case must contain a claim support decision')
    contrast = {'kind': finding.contrast.kind}
    if finding.contrast.value is not None:
        contrast['value'] = format_rational(finding.contrast.value)
    return {'excluded_batch': finding.excluded_batch, 'contrast': contrast,
            'supports_claim': finding.supports_claim}


def report_body(result: ReviewResult) -> dict:
    if not isinstance(result, ReviewResult):
        raise ValueError('a complete ReviewResult is required')
    contrast = parse_pair(result.contrast, 'contrast')
    claim = parse_pair(result.claim, 'claim')
    cases = [_case_body(finding) for finding in result.findings]
    return {
        'run_id': result.run_id,
        'parents': list(result.parents),
        'parent_checksums': list(result.parent_checksums),
        'contrast': [format_rational(value) for value in contrast],
        'claim': [format_rational(value) for value in claim],
        'cases': cases,
        'supporting_cases': list(result.supporting_cases),
        'supported': result.supported,
    }
