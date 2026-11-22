from dataclasses import dataclass

from registry.eligibility import BatchEligibility


def validate_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{label} must be a nonempty identifier without surrounding whitespace')
    return value


@dataclass(frozen=True, slots=True)
class ReferenceBatch:
    batch_id: str
    eligibility: BatchEligibility
    unit: str


@dataclass(frozen=True, slots=True)
class ReferenceRoster:
    run_id: str
    batches: tuple[ReferenceBatch, ...]
    digest: str

    def batch(self, batch_id: str) -> ReferenceBatch:
        validate_identifier(batch_id, 'batch ID')
        for batch in self.batches:
            if batch.batch_id == batch_id:
                return batch
        raise KeyError(batch_id)
