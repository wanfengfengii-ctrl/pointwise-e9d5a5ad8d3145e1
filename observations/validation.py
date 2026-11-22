from collections.abc import Mapping

from observations.equations import ObservationEquation, normalize_equation
from registry.references import ReferenceRoster


_ROW_FIELDS = {'batch', 'unit', 'coefficients', 'reading'}


def validate_observation_rows(roster: ReferenceRoster, rows) -> tuple[ObservationEquation, ...]:
    if not isinstance(rows, (list, tuple)):
        raise ValueError('observations must be an ordered list')
    normalized = []
    for line, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping) or set(row) != _ROW_FIELDS:
            raise ValueError(f'observation {line} requires batch, unit, coefficients, and reading')
        try:
            batch = roster.batch(row['batch'])
            equation = normalize_equation(batch.batch_id, row['coefficients'], row['reading'], row['unit'])
        except (KeyError, ValueError) as error:
            raise ValueError(f'invalid observation {line}: {error}') from error
        normalized.append(equation)
    return tuple(normalized)
