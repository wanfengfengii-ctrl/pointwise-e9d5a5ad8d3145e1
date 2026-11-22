"""Drift pieces: version 2 station evidence with a shared drift coordinate.

A drift piece carries the issuer identity, the normalized work box, and
the per-case public feasible sets over ``(x, y, z)``.  Original rows,
private zero-offsets, and certified bounds stay at the station.  The
checksum is the SHA-256 of the canonical JSON body without ``checksum``
and doubles as the centre intake key.
"""
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from evidence.envelope import validate_digest
from evidence.polyhedra import PublicRelation, _normalize_row
from evidence.relations import reduce_equations
from observations.rationals import format_rational, parse_rational
from observations.revisions import validate_revision_id, validate_station
from publication.receipts import canonical_json
from registry.references import validate_identifier


@dataclass(frozen=True, slots=True)
class DriftPiece:
    run_id: str
    station: str
    revision_id: int
    roster_digest: str
    work_box: tuple
    cases: tuple
    checksum: str

    @property
    def case_ids(self) -> tuple:
        return tuple(excluded for excluded, _ in self.cases)


def parse_interval(value, label: str):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f'{label} requires a two-element closed interval')
    try:
        low, high = parse_rational(value[0]), parse_rational(value[1])
    except ValueError as error:
        raise ValueError(f'invalid {label}: {error}') from error
    if low > high:
        raise ValueError(f'{label} must not start above its end')
    return low, high


def parse_work_box(work_box) -> tuple:
    if not isinstance(work_box, Mapping) or set(work_box) != {'x', 'y', 'z'}:
        raise ValueError('the work box requires exactly the x, y, and z intervals')
    return tuple(parse_interval(work_box[axis], f'work box {axis!r}') for axis in ('x', 'y', 'z'))


def parse_certified_bounds(certified_bounds) -> dict:
    if not isinstance(certified_bounds, Mapping):
        raise ValueError('certified bounds must map private symbols to closed intervals')
    if len(certified_bounds) > 2:
        raise ValueError('at most two private symbols may carry certified bounds')
    parsed = {}
    for symbol, interval in certified_bounds.items():
        if (not isinstance(symbol, str) or not symbol.isidentifier()
                or symbol in ('x', 'y', 'ref_shift')):
            raise ValueError(f'invalid certified symbol: {symbol!r}')
        parsed[symbol] = parse_interval(interval, f'certified bound {symbol!r}')
    return parsed


def _validate_interval_pair(pair, label: str):
    if (not isinstance(pair, tuple) or len(pair) != 2
            or any(not isinstance(value, Fraction) for value in pair)):
        raise ValueError(f'invalid {label}')
    low, high = pair
    if low > high:
        raise ValueError(f'{label} must not start above its end')
    return low, high


def _validate_work_box(work_box) -> tuple:
    if not isinstance(work_box, tuple) or len(work_box) != 3:
        raise ValueError('the work box requires exactly the x, y, and z intervals')
    return tuple(_validate_interval_pair(pair, 'work box interval') for pair in work_box)


def _validate_row(row) -> None:
    if (not isinstance(row, tuple) or len(row) != 4
            or any(not isinstance(value, Fraction) for value in row)):
        raise ValueError('invalid relation row')


def _validate_relation(relation) -> None:
    if not isinstance(relation, PublicRelation) or type(relation.empty) is not bool:
        raise ValueError('invalid public relation')
    if relation.empty:
        if relation.equalities or relation.inequalities:
            raise ValueError('an empty relation must not list constraints')
        return
    for row in relation.equalities:
        _validate_row(row)
    if reduce_equations(relation.equalities, 3) != relation.equalities:
        raise ValueError('relation equalities must be in canonical reduced form')
    previous = None
    for row in relation.inequalities:
        _validate_row(row)
        if not any(row[:3]):
            raise ValueError('an inequality requires a nonzero coefficient')
        if _normalize_row(row) != row:
            raise ValueError('relation inequalities must be normalized')
        if previous is not None and previous >= row:
            raise ValueError('relation inequalities must be ordered and distinct')
        previous = row


def _validate_cases(cases) -> None:
    if not cases or cases[0][0] is not None:
        raise ValueError('the first case must retain all observations')
    seen = {None}
    for index, (excluded, relation) in enumerate(cases):
        if index:
            validate_identifier(excluded, 'excluded batch')
            if excluded in seen:
                raise ValueError('duplicate exclusion case')
            seen.add(excluded)
        _validate_relation(relation)


def _hash(document) -> str:
    return hashlib.sha256(canonical_json(document).encode('utf-8')).hexdigest()


def _encode_relation(relation: PublicRelation) -> dict:
    return {
        'empty': relation.empty,
        'equalities': [[format_rational(value) for value in row] for row in relation.equalities],
        'inequalities': [[format_rational(value) for value in row] for row in relation.inequalities],
    }


def _payload(run_id, station, revision_id, roster_digest, work_box, cases) -> dict:
    return {
        'version': 2,
        'run_id': run_id,
        'station': station,
        'revision_id': revision_id,
        'roster_digest': roster_digest,
        'work_box': {axis: [format_rational(low), format_rational(high)]
                     for axis, (low, high) in zip(('x', 'y', 'z'), work_box)},
        'cases': [{'excluded_batch': excluded, 'relation': _encode_relation(relation)}
                  for excluded, relation in cases],
    }


def seal_drift_piece(run_id: str, station: str, revision_id: int, roster_digest: str,
                     work_box, cases) -> DriftPiece:
    validate_identifier(run_id, 'run ID')
    validate_station(station)
    validate_revision_id(revision_id)
    validate_digest(roster_digest, 'roster digest')
    work_box = _validate_work_box(work_box)
    cases = tuple((excluded, relation) for excluded, relation in cases)
    _validate_cases(cases)
    checksum = _hash(_payload(run_id, station, revision_id, roster_digest, work_box, cases))
    return DriftPiece(run_id, station, revision_id, roster_digest, work_box, cases, checksum)


def _document(piece: DriftPiece) -> dict:
    payload = _payload(piece.run_id, piece.station, piece.revision_id,
                       piece.roster_digest, piece.work_box, piece.cases)
    return {**payload, 'checksum': piece.checksum}


def encode_drift_piece(piece: DriftPiece) -> str:
    return canonical_json(_document(piece))


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON field: {key}')
        result[key] = value
    return result


def _decode_rows(value, label: str) -> tuple:
    if not isinstance(value, list):
        raise ValueError(f'invalid {label} encoding')
    rows = []
    for item in value:
        if not isinstance(item, list) or len(item) != 4:
            raise ValueError(f'invalid {label} row')
        rows.append(tuple(parse_rational(cell) for cell in item))
    return tuple(rows)


def _decode_relation(value) -> PublicRelation:
    if not isinstance(value, dict) or set(value) != {'empty', 'equalities', 'inequalities'}:
        raise ValueError('invalid relation encoding')
    if type(value['empty']) is not bool:
        raise ValueError('invalid relation encoding')
    return PublicRelation(value['empty'], _decode_rows(value['equalities'], 'equality'),
                          _decode_rows(value['inequalities'], 'inequality'))


def _decode_case(item) -> tuple:
    if not isinstance(item, dict) or set(item) != {'excluded_batch', 'relation'}:
        raise ValueError('invalid case encoding')
    return item['excluded_batch'], _decode_relation(item['relation'])


def decode_drift_piece(encoded: str) -> DriftPiece:
    if not isinstance(encoded, str):
        raise ValueError('a drift piece must be JSON text')
    try:
        document = json.loads(encoded, object_pairs_hook=_unique_keys)
        if (not isinstance(document, dict) or type(document.get('version')) is not int
                or document['version'] != 2):
            raise ValueError('unsupported drift piece version')
        box = document['work_box']
        if not isinstance(box, dict) or set(box) != {'x', 'y', 'z'}:
            raise ValueError('invalid work box encoding')
        work_box = tuple(parse_interval(box[axis], 'work box') for axis in ('x', 'y', 'z'))
        if not isinstance(document['cases'], list):
            raise ValueError('cases must be an ordered list')
        cases = tuple(_decode_case(item) for item in document['cases'])
        piece = seal_drift_piece(document['run_id'], document['station'], document['revision_id'],
                                 document['roster_digest'], work_box, cases)
    except (KeyError, TypeError, UnicodeError) as error:
        raise ValueError('invalid drift piece structure') from error
    if document != _document(piece):
        raise ValueError('drift piece identity, encoding, or checksum does not match')
    return piece
