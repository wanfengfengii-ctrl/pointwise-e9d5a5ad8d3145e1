import sqlite3
import tempfile
import unittest
from pathlib import Path

from evidence.handoff import export_piece, load_piece
from evidence.issue import issue
from observations.intake import revise
from observations.revisions import RevisionStore
from publication.store import PublicationStore
from registry.runs import RunCatalog
from review.intake import IntakeStore, receive


def batch(batch_id, eligibility='trusted', unit='μm'):
    return {'batch_id': batch_id, 'eligibility': eligibility, 'unit': unit}


def obs(batch_id, reading, *, unit='μm', **coefficients):
    return {'batch': batch_id, 'reading': reading, 'unit': unit, 'coefficients': coefficients}


class LabCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.open_sources()
        self.open_centre()

    def connect(self, filename):
        connection = sqlite3.connect(self.root / filename)
        self.addCleanup(connection.close)
        return connection

    def open_sources(self):
        self.catalog = RunCatalog(self.connect('catalog.sqlite'))
        self.catalog.initialize()
        self.revisions = {}
        for station in ('A', 'B'):
            store = RevisionStore(self.connect(f'station-{station}.sqlite'))
            store.initialize()
            self.revisions[station] = store

    def close_sources(self):
        self.catalog.db.close()
        for store in self.revisions.values():
            store.db.close()

    def open_centre(self):
        self.centre = self.connect('centre.sqlite')
        self.intake = IntakeStore(self.centre)
        self.publication = PublicationStore(self.centre)
        self.intake.initialize()
        self.publication.initialize()

    def freeze(self, station, rows, *, run='R', previous=None):
        return revise(self.catalog, self.revisions[station], station, run, rows, previous)

    def issue(self, revision):
        store = self.revisions[revision.station]
        return issue(self.catalog, store, revision.revision_id)

    def deliver(self, revision):
        piece = self.issue(revision)
        file = self.root / f'{piece.piece_id}.json'
        return receive(self.intake, load_piece(export_piece(piece, file)))

    def freeze_pair(self, left, right, *, run='R'):
        return self.freeze('A', left, run=run), self.freeze('B', right, run=run)

    def publication_counts(self):
        return tuple(self.centre.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                     for table in ('reports', 'report_parents', 'receipts'))
