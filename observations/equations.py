from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from observations.rationals import parse_rational
from registry.units import convert_to_micrometres


@dataclass(frozen=True, slots=True)
class ObservationEquation:
    batch_id: str
    coefficients: tuple[tuple[str, Fraction], ...]
    reading_um: Fraction


def normalize_equation(batch_id: str, coefficients: Mapping, reading, unit: str) -> ObservationEquation:
    if not isinstance(coefficients, Mapping):
        raise ValueError('coefficients must map symbols to rationals')
    terms = []
    for symbol, value in coefficients.items():
        if not isinstance(symbol, str) or not symbol.isidentifier():
            raise ValueError(f'invalid observation symbol: {symbol!r}')
        coefficient = parse_rational(value)
        if coefficient:
            terms.append((symbol, coefficient))
    reading_um = convert_to_micrometres(parse_rational(reading), unit)
    return ObservationEquation(batch_id, tuple(sorted(terms)), reading_um)
