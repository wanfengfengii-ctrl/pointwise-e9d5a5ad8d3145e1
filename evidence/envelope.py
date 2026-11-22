import hashlib
import json
import re
from dataclasses import dataclass

from evidence.relations import AffineRelation
from observations.rationals import format_rational, parse_rational
from observations.revisions import validate_revision_id, validate_station
from registry.references import validate_identifier


CaseRelations = tuple[tuple[str | None, AffineRelation], ...]
_DIGEST = re.compile('[0-9a-f]{64}')


@dataclass(frozen=True, slots=True)
class PieceEnvelope:
    piece_id: str
    run_id: str
    station: str
    revision_id: int
    roster_digest: str
    cases: CaseRelations
    checksum: str

    @property
    def case_ids(self) -> tuple[str | None, ...]:
        return tuple(excluded for excluded, _ in self.cases)


def validate_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f'invalid {label}')


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value) -> str:
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _payload(piece_id, run_id, station, revision_id, roster_digest, cases):
    return {
        'version': 1, 'piece_id': piece_id, 'run_id': run_id, 'station': station,
        'revision_id': revision_id, 'roster_digest': roster_digest,
        'cases': [
            {'excluded_batch': excluded, 'consistent': relation.consistent,
             'equations': [[format_rational(value) for value in row] for row in relation.equations]}
            for excluded, relation in cases
        ],
    }


def _validate_cases(cases: CaseRelations) -> None:
    if not cases or cases[0][0] is not None:
        raise ValueError('the first case must retain all observations')
    seen = {None}
    for index, (excluded, relation) in enumerate(cases):
        if index:
            validate_identifier(excluded, 'excluded batch')
            if excluded in seen:
                raise ValueError('duplicate exclusion case')
            seen.add(excluded)
        if not isinstance(relation, AffineRelation) or type(relation.consistent) is not bool:
            raise ValueError('invalid affine relation')
        if relation.consistent:
            if AffineRelation.from_rows(relation.equations) != relation:
                raise ValueError('relation equations must be in canonical reduced form')
        elif relation.equations != ():
            raise ValueError('an inconsistent relation must have no equations')


def seal_envelope(run_id: str, station: str, revision_id: int, roster_digest: str,
                  cases: CaseRelations) -> PieceEnvelope:
    validate_identifier(run_id, 'run ID')
    validate_station(station)
    validate_revision_id(revision_id)
    validate_digest(roster_digest, 'roster digest')
    cases = tuple((excluded, relation) for excluded, relation in cases)
    _validate_cases(cases)
    piece_id = _hash([run_id, station, revision_id])
    payload = _payload(piece_id, run_id, station, revision_id, roster_digest, cases)
    return PieceEnvelope(piece_id, run_id, station, revision_id, roster_digest, cases, _hash(payload))


def _document(piece: PieceEnvelope) -> dict:
    payload = _payload(piece.piece_id, piece.run_id, piece.station, piece.revision_id,
                       piece.roster_digest, piece.cases)
    return {**payload, 'checksum': piece.checksum}


def encode_envelope(piece: PieceEnvelope) -> str:
    return _canonical(_document(piece))


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON field: {key}')
        result[key] = value
    return result


def _parse_case(item):
    if not isinstance(item, dict) or type(item.get('consistent')) is not bool:
        raise ValueError('invalid case encoding')
    equations = item['equations']
    if not isinstance(equations, list) or any(not isinstance(row, list) for row in equations):
        raise ValueError('invalid equation encoding')
    rows = tuple(tuple(parse_rational(value) for value in row) for row in equations)
    return item['excluded_batch'], AffineRelation(item['consistent'], rows)


def decode_envelope(encoded: str) -> PieceEnvelope:
    if not isinstance(encoded, str):
        raise ValueError('a station piece must be JSON text')
    try:
        document = json.loads(encoded, object_pairs_hook=_unique_keys)
        if not isinstance(document, dict) or type(document.get('version')) is not int or document['version'] != 1:
            raise ValueError('unsupported station piece version')
        if not isinstance(document['cases'], list):
            raise ValueError('cases must be an ordered list')
        cases = tuple(_parse_case(item) for item in document['cases'])
        piece = seal_envelope(document['run_id'], document['station'], document['revision_id'],
                              document['roster_digest'], cases)
    except (KeyError, TypeError, UnicodeError) as error:
        raise ValueError('invalid station piece structure') from error
    if document != _document(piece):
        raise ValueError('station piece identity, encoding, or checksum does not match')
    return piece
