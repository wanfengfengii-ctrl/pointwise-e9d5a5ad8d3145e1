from dataclasses import dataclass
from fractions import Fraction

from observations.rationals import parse_rational


PublicEquation = tuple[Fraction, Fraction, Fraction]


def reduce_equations(rows, variable_count: int):
    """Return reduced augmented rows, or None for inconsistent equalities."""
    matrix = []
    for row in rows:
        values = [parse_rational(value) for value in row]
        if len(values) != variable_count + 1:
            raise ValueError('wrong augmented row width')
        matrix.append(values)

    rank = 0
    for column in range(variable_count):
        pivot = next((index for index in range(rank, len(matrix)) if matrix[index][column]), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        divisor = matrix[rank][column]
        basis = [value / divisor for value in matrix[rank]]
        matrix[rank] = basis
        for index, row in enumerate(matrix):
            if index != rank and row[column]:
                factor = row[column]
                matrix[index] = [value - factor * base for value, base in zip(row, basis)]
        rank += 1
    if any(row[-1] for row in matrix[rank:]):
        return None
    return tuple(tuple(row) for row in matrix[:rank])


@dataclass(frozen=True, slots=True)
class AffineRelation:
    consistent: bool
    equations: tuple[PublicEquation, ...] = ()

    @classmethod
    def from_rows(cls, rows):
        reduced = reduce_equations(rows, 2)
        return cls(False) if reduced is None else cls(True, reduced)

    def contains(self, pair: tuple[Fraction, Fraction]) -> bool:
        x, y = pair
        return self.consistent and all(a * x + b * y == rhs for a, b, rhs in self.equations)


def intersect_relations(left: AffineRelation, right: AffineRelation) -> AffineRelation:
    if not left.consistent or not right.consistent:
        return AffineRelation(False)
    return AffineRelation.from_rows(left.equations + right.equations)
