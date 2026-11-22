import re
from fractions import Fraction


_RATIONAL = re.compile(r'[+-]?[0-9]+(?:/[+-]?[0-9]+)?')


def parse_rational(value: int | str | Fraction) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Fraction(value)
    if not isinstance(value, str) or not _RATIONAL.fullmatch(value):
        raise ValueError('expected an integer or an exact rational string')
    numerator, slash, denominator = value.partition('/')
    try:
        return Fraction(int(numerator), int(denominator) if slash else 1)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f'invalid rational: {value!r}') from error


def format_rational(value: Fraction | int) -> str:
    return str(parse_rational(value))
