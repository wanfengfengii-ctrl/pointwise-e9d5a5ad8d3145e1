"""Exact rational polyhedra over the public drift coordinates.

A PublicRelation describes one station case as linear equalities and
``<=`` inequalities over the shared public coordinates ``(x, y, z)``.
Rows are tuples of :class:`fractions.Fraction`; the last entry is the
right-hand side.  Fourier-Motzkin elimination with exact rationals
projects private zero-offsets away at issue time and evaluates exact
contrast ranges over the joint feasible set at signing time.
"""
import math
from dataclasses import dataclass
from fractions import Fraction

from evidence.relations import reduce_equations


@dataclass(frozen=True, slots=True)
class PublicRelation:
    empty: bool
    equalities: tuple = ()
    inequalities: tuple = ()


def _normalize_row(row):
    """Rescale an augmented row to coprime integers (positive scaling)."""
    scale = math.lcm(*(value.denominator for value in row))
    integers = tuple(int(value * scale) for value in row)
    divisor = math.gcd(*integers)
    return tuple(Fraction(value // divisor) for value in integers)


def _substitute(rows, index, pivot):
    base = pivot[index]
    substituted = []
    for row in rows:
        coeff = row[index]
        if coeff:
            factor = coeff / base
            substituted.append(tuple(value - factor * pivot_value
                                     for value, pivot_value in zip(row, pivot)))
        else:
            substituted.append(row)
    return substituted


def _eliminate(equalities, inequalities, index):
    """Eliminate the variable at ``index`` exactly from the system."""
    pivot_at = next((at for at, row in enumerate(equalities) if row[index]), None)
    if pivot_at is not None:
        pivot = equalities[pivot_at]
        rest = equalities[:pivot_at] + equalities[pivot_at + 1:]
        return tuple(_substitute(rest, index, pivot)), tuple(_substitute(inequalities, index, pivot))
    lowers, uppers, kept = [], [], []
    for row in inequalities:
        coeff = row[index]
        if coeff > 0:
            uppers.append(row)
        elif coeff < 0:
            lowers.append(row)
        else:
            kept.append(row)
    combined = kept
    for lower in lowers:
        for upper in uppers:
            combined.append(tuple(upper[index] * low + (-lower[index]) * high
                                  for low, high in zip(lower, upper)))
    return tuple(equalities), tuple(combined)


def _simplify(inequalities):
    """Normalize and deduplicate rows; ``None`` signals a trivial conflict."""
    seen = {}
    for row in inequalities:
        if not any(row[:-1]):
            if row[-1] < 0:
                return None
            continue
        seen.setdefault(_normalize_row(row))
    return tuple(seen)


def _eliminate_all(equalities, inequalities, indices):
    equalities = tuple(equalities)
    inequalities = tuple(inequalities)
    for index in indices:
        equalities, inequalities = _eliminate(equalities, inequalities, index)
        inequalities = _simplify(inequalities)
        if inequalities is None:
            return equalities, None
    return equalities, inequalities


def project_public_relation(rows, work_box, certified_bounds) -> PublicRelation:
    """Project one case of effective rows onto the public ``(x, y, z)`` space.

    ``ref_shift`` denotes the shared drift coordinate ``z``; every other
    non-public symbol is a private zero-offset of this station.  Certified
    bounds constrain their symbols; all other private symbols are free.
    """
    rows = tuple(rows)
    private = sorted({name for row in rows for name, _ in row.coefficients
                      if name not in ('x', 'y', 'ref_shift')})
    index_of = {name: at for at, name in enumerate(('x', 'y', 'z', *private))}
    width = len(index_of)
    equalities = []
    for row in rows:
        coeffs = [Fraction(0)] * width
        for name, value in row.coefficients:
            coeffs[index_of['z' if name == 'ref_shift' else name]] += value
        equalities.append(tuple(coeffs) + (row.reading_um,))
    inequalities = []

    def add_bound(at, coeff, rhs):
        row = [Fraction(0)] * width
        row[at] = Fraction(coeff)
        inequalities.append(tuple(row) + (Fraction(rhs),))

    for axis, (low, high) in enumerate(work_box):
        add_bound(axis, -1, -low)
        add_bound(axis, 1, high)
    for symbol in sorted(certified_bounds):
        at = index_of.get(symbol)
        if at is None:
            continue
        low, high = certified_bounds[symbol]
        add_bound(at, -1, -low)
        add_bound(at, 1, high)
    equalities, inequalities = _eliminate_all(equalities, inequalities,
                                              range(3, width))
    if inequalities is None:
        return PublicRelation(True)
    reduced = reduce_equations([row[:3] + row[-1:] for row in equalities], 3)
    if reduced is None:
        return PublicRelation(True)
    relation = PublicRelation(False, tuple(tuple(row) for row in reduced),
                              tuple(sorted(row[:3] + row[-1:] for row in inequalities)))
    if not _feasible(relation.equalities, relation.inequalities):
        return PublicRelation(True)
    return relation


def _feasible(equalities, inequalities) -> bool:
    equalities, inequalities = _eliminate_all(equalities, inequalities, range(3))
    if inequalities is None:
        return False
    return not any(row[-1] for row in equalities)


def contrast_range(equalities, inequalities, coefficients):
    """Exact ``[min, max]`` of ``a*x + b*y`` over the joint system.

    Returns ``None`` when the combined system has no feasible point.
    """
    a, b = coefficients
    eqs = [tuple(row[:3]) + (Fraction(0), row[3]) for row in equalities]
    eqs.append((-a, -b, Fraction(0), Fraction(1), Fraction(0)))
    ineqs = [tuple(row[:3]) + (Fraction(0), row[3]) for row in inequalities]
    eqs, ineqs = _eliminate_all(eqs, ineqs, range(3))
    if ineqs is None:
        return None
    fixed = None
    for row in eqs:
        coeff, rhs = row[3], row[4]
        if not coeff:
            if rhs:
                return None
            continue
        value = rhs / coeff
        if fixed is None:
            fixed = value
        elif fixed != value:
            return None
    if fixed is not None:
        if all(row[3] * fixed <= row[4] for row in ineqs):
            return fixed, fixed
        return None
    lower = upper = None
    for row in ineqs:
        coeff, rhs = row[3], row[4]
        if not coeff:
            if rhs < 0:
                return None
            continue
        bound = rhs / coeff
        if coeff > 0:
            upper = bound if upper is None else min(upper, bound)
        else:
            lower = bound if lower is None else max(lower, bound)
    if lower is None or upper is None:
        raise ValueError('the contrast range is unbounded over the joint feasible set')
    if lower > upper:
        return None
    return lower, upper
