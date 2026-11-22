from fractions import Fraction


_UNIT_ALIASES = {'um': 'μm', 'µm': 'μm'}
_MICROMETRES = {'μm': Fraction(1), 'mm': Fraction(1000), 'nm': Fraction(1, 1000)}


def validate_unit(unit: str) -> str:
    if not isinstance(unit, str):
        raise ValueError('unit must be a supported length unit')
    canonical = _UNIT_ALIASES.get(unit, unit)
    if canonical not in _MICROMETRES:
        raise ValueError(f'unsupported length unit: {unit!r}')
    return canonical


def convert_to_micrometres(value: Fraction | int, unit: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (Fraction, int)):
        raise ValueError('unit conversion requires an exact rational')
    return value * _MICROMETRES[validate_unit(unit)]
