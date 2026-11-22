import json
import sqlite3
from dataclasses import dataclass, field
from fractions import Fraction

from observations.equations import ObservationEquation
from observations.rationals import format_rational, parse_rational
from registry.references import validate_identifier


@dataclass(frozen=True, slots=True)
class StationRevision:
    revision_id: int
    station: str
    run_id: str
    previous: int | None
    rows: tuple[ObservationEquation, ...]
    _original_json: str = field(repr=False)

    @property
    def original_rows(self) -> list[dict]:
        return json.loads(self._original_json)


def validate_station(station: str) -> None:
    if station not in ('A', 'B'):
        raise ValueError('station must be A or B')


def validate_revision_id(revision_id: int) -> None:
    if type(revision_id) is not int or not 1 <= revision_id <= 2**63 - 1:
        raise ValueError('invalid revision ID')


def _serialize_rows(rows):
    return json.dumps([
        [row.batch_id, [[symbol, format_rational(value)] for symbol, value in row.coefficients],
         format_rational(row.reading_um)]
        for row in rows
    ], ensure_ascii=False, separators=(',', ':'))


def _decode_rows(encoded):
    return tuple(
        ObservationEquation(batch, tuple((symbol, parse_rational(value)) for symbol, value in terms),
                            parse_rational(reading))
        for batch, terms, reading in json.loads(encoded)
    )


def _raw_value(value):
    return format_rational(value) if isinstance(value, Fraction) else value


def _capture_original(rows):
    return json.dumps([
        {'batch': row['batch'], 'unit': row['unit'], 'reading': _raw_value(row['reading']),
         'coefficients': {symbol: _raw_value(value) for symbol, value in row['coefficients'].items()}}
        for row in rows
    ], ensure_ascii=False, separators=(',', ':'))


class RevisionStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS station_revisions (
                revision_id INTEGER PRIMARY KEY,
                station TEXT NOT NULL CHECK (station IN ('A', 'B')),
                run_id TEXT NOT NULL,
                previous INTEGER REFERENCES station_revisions(revision_id),
                equations TEXT NOT NULL,
                original_rows TEXT NOT NULL
            )
        ''')
        self.db.execute('''
            CREATE INDEX IF NOT EXISTS station_revision_scope
            ON station_revisions (station, run_id, revision_id)
        ''')

    def freeze(self, station: str, run_id: str, rows: tuple[ObservationEquation, ...],
               original_rows, previous: int | None = None) -> StationRevision:
        validate_station(station)
        validate_identifier(run_id, 'run ID')
        if len(rows) != len(original_rows):
            raise ValueError('the original and normalized row counts differ')
        if previous is not None:
            parent = self.get(previous)
            if (parent.station, parent.run_id) != (station, run_id):
                raise ValueError('previous revision belongs to a different station or run')
        equations = _serialize_rows(rows)
        originals = _capture_original(original_rows)
        if self.db.in_transaction:
            raise ValueError('freezing requires a connection without a pending transaction')
        with self.db:
            cursor = self.db.execute('''
                INSERT INTO station_revisions (station, run_id, previous, equations, original_rows)
                VALUES (?, ?, ?, ?, ?)
            ''', (station, run_id, previous, equations, originals))
        return StationRevision(cursor.lastrowid, station, run_id, previous, tuple(rows), originals)

    def get(self, revision_id: int) -> StationRevision:
        validate_revision_id(revision_id)
        row = self.db.execute('''
            SELECT station, run_id, previous, equations, original_rows
            FROM station_revisions WHERE revision_id = ?
        ''', (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        station, run_id, previous, equations, originals = row
        return StationRevision(revision_id, station, run_id, previous, _decode_rows(equations), originals)

    def list_revisions(self, station: str, run_id: str) -> tuple[int, ...]:
        validate_station(station)
        validate_identifier(run_id, 'run ID')
        return tuple(row[0] for row in self.db.execute('''
            SELECT revision_id FROM station_revisions WHERE station = ? AND run_id = ?
            ORDER BY revision_id
        ''', (station, run_id)))
