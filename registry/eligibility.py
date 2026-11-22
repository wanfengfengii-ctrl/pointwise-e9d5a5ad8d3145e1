from enum import StrEnum


class BatchEligibility(StrEnum):
    TRUSTED = 'trusted'
    CANDIDATE = 'candidate'


def parse_eligibility(value: str) -> BatchEligibility:
    try:
        return BatchEligibility(value)
    except (TypeError, ValueError) as error:
        raise ValueError('eligibility must be trusted or candidate') from error


def eligible_batch_ids(roster) -> tuple[str, ...]:
    return tuple(
        batch.batch_id for batch in roster.batches
        if batch.eligibility is BatchEligibility.CANDIDATE
    )
