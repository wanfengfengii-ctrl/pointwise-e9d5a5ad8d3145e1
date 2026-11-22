from dataclasses import dataclass
from fractions import Fraction

from evidence.relations import AffineRelation


@dataclass(frozen=True, slots=True)
class ContrastRange:
    value: Fraction | None

    @property
    def kind(self) -> str:
        return 'all_rationals' if self.value is None else 'fixed'


def evaluate_contrast(relation: AffineRelation, coefficients: tuple[Fraction, Fraction]) -> ContrastRange:
    if not relation.consistent:
        raise ValueError('contrast requires a feasible relation')
    a, b = coefficients
    value = Fraction(0)
    for x, y, rhs in relation.equations:
        factor = a if x else b
        a -= factor * x
        b -= factor * y
        value += factor * rhs
    return ContrastRange(None if a or b else value)


def supports_claim(relation: AffineRelation, claim: tuple[Fraction, Fraction]) -> bool:
    return relation.contains(claim)
