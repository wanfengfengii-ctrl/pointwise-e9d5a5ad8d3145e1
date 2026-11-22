import hashlib
import json
import sqlite3
from collections.abc import Mapping

from registry.eligibility import parse_eligibility
from registry.references import ReferenceBatch, ReferenceRoster, validate_identifier
from registry.units import validate_unit


def _normalize_batches(batches):
    if not isinstance(batches, (list, tuple)):
        raise ValueError('batches must be an ordered list')
    normalized = []
    seen = set()
    for entry in batches:
        if not isinstance(entry, Mapping) or set(entry) != {'batch_id', 'eligibility', 'unit'}:
            raise ValueError('each batch requires batch_id, eligibility, and unit')
        batch_id = validate_identifier(entry['batch_id'], 'batch ID')
        if batch_id in seen:
            raise ValueError(f'duplicate batch ID: {batch_id}')
        seen.add(batch_id)
        normalized.append([batch_id, parse_eligibility(entry['eligibility']).value,
                           validate_unit(entry['unit'])])
    return json.dumps(normalized, ensure_ascii=False, separators=(',', ':'))


def _roster(run_id: str, stored: str) -> ReferenceRoster:
    batches = tuple(
        ReferenceBatch(batch_id, parse_eligibility(eligibility), unit)
        for batch_id, eligibility, unit in json.loads(stored)
    )
    digest = hashlib.sha256(stored.encode('utf-8')).hexdigest()
    return ReferenceRoster(run_id, batches, digest)


class RunCatalog:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('CREATE TABLE IF NOT EXISTS run_rosters (run_id TEXT PRIMARY KEY, batches TEXT NOT NULL)')

    def register(self, run_id: str, batches) -> ReferenceRoster:
        validate_identifier(run_id, 'run ID')
        encoded = _normalize_batches(batches)
        if self.db.in_transaction:
            raise ValueError('registration requires a connection without a pending transaction')
        with self.db:
            self.db.execute(
                'INSERT INTO run_rosters VALUES (?, ?) ON CONFLICT(run_id) DO NOTHING',
                (run_id, encoded),
            )
            stored = self._get_batches(run_id)
            if stored != encoded:
                raise ValueError(f'conflicting roster for run {run_id!r}')
        return _roster(run_id, stored)

    def _get_batches(self, run_id: str) -> str:
        row = self.db.execute('SELECT batches FROM run_rosters WHERE run_id = ?', (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return row[0]

    def get(self, run_id: str) -> ReferenceRoster:
        validate_identifier(run_id, 'run ID')
        return _roster(run_id, self._get_batches(run_id))
