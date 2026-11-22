from collections.abc import Iterable

from evidence.relations import AffineRelation, reduce_equations
from observations.equations import ObservationEquation


def project_public(rows: Iterable[ObservationEquation]) -> AffineRelation:
    rows = tuple(rows)
    private = sorted({name for row in rows for name, _ in row.coefficients if name not in ('x', 'y')})
    symbols = (*private, 'x', 'y')
    augmented = []
    for row in rows:
        terms = dict(row.coefficients)
        augmented.append(tuple(terms.get(name, 0) for name in symbols) + (row.reading_um,))

    reduced = reduce_equations(augmented, len(symbols))
    if reduced is None:
        return AffineRelation(False)
    # Putting private columns first leaves precisely the public-only equations
    # after their pivot rows. Private pivot equations then admit an extension.
    width = len(private)
    public = tuple(row[width:] for row in reduced if not any(row[:width]))
    return AffineRelation(True, public)
