import sqlite3
from fractions import Fraction

from evidence.envelope import encode_envelope
from evidence.handoff import export_piece, load_piece
from evidence.issue import issue
from review.intake import receive
from tests import LabCase, batch, obs


class PrepareTests(LabCase):
    def test_frozen_revisions_issue_and_receive(self):
        self.catalog.register('R', [batch('T')])
        a, b = self.freeze_pair([obs('T', 1, x=1)], [obs('T', 2, y=1)])
        received = tuple(self.deliver(revision) for revision in (a, b))
        self.assertEqual([(entry.piece.run_id, entry.piece.station, entry.piece.revision_id) for entry in received],
                         [('R', 'A', a.revision_id), ('R', 'B', b.revision_id)])
        self.assertNotEqual(received[0].key, received[1].key)
        with self.assertRaises(KeyError):
            issue(self.catalog, self.revisions['B'], b.revision_id + 1)

    def test_catalog_replay(self):
        entries = [batch('H'), batch('G', 'candidate', 'um')]
        first = self.catalog.register('R', entries)
        self.assertEqual(self.catalog.register('R', [batch('H'), batch('G', 'candidate')]), first)
        with self.assertRaises(ValueError):
            self.catalog.register('R', [batch('H'), batch('G')])
        with self.assertRaises(ValueError):
            self.catalog.register('R', [batch('G', 'candidate'), batch('H')])
        with self.assertRaises(ValueError):
            self.catalog.register('other', [batch('H', unit='inch')])
        with self.assertRaises(KeyError):
            self.catalog.get('other')
        self.assertEqual(self.catalog.get('R'), first)
        self.assertEqual(self.catalog.get('R').batch('G').eligibility.value, 'candidate')

    def test_exact_units(self):
        self.catalog.register('R', [batch('T'), batch('M', unit='mm')])
        source = [obs('M', '3/1000', unit='mm', y=1),
                  obs('T', '1/3000', unit='mm', x=1),
                  obs('T', 3000, unit='nm', y=1)]
        a = self.freeze('A', source)
        persisted = self.revisions['A'].get(a.revision_id)
        self.assertEqual(persisted.original_rows, source)
        self.assertEqual(tuple(row.reading_um for row in persisted.rows), (3, Fraction(1, 3), 3))
        piece = self.deliver(a).piece
        self.assertEqual(piece.cases[0][1].equations, ((1, 0, Fraction(1, 3)), (0, 1, 3)))

    def test_fixed_envelope_round_trip_keeps_private_observations_on_site(self):
        self.catalog.register('R', [batch('T')])
        a = self.freeze('A', [obs('T', 5, private_offset_87=1, x=1),
                              obs('T', 4, private_offset_87=1)])
        piece = self.issue(a)
        encoded = encode_envelope(piece)
        self.assertNotIn('private_offset_87', encoded)
        self.assertNotIn('reading', encoded)
        self.assertNotIn('coefficients', encoded)
        location = self.root / 'A-piece.json'
        loaded = load_piece(export_piece(piece, location))
        self.assertEqual(loaded, piece)
        self.assertEqual((loaded.station, loaded.run_id, loaded.revision_id), ('A', 'R', a.revision_id))
        first = receive(self.intake, loaded)
        self.assertEqual(receive(self.intake, encoded), first)
        self.assertEqual(self.intake.get(first.key), first)
        self.assertEqual(loaded.cases[0][1].equations, ((1, 0, 1),))

    def assert_rejected_batch(self, bad_row):
        self.catalog.register('R', [batch('T')])
        original = self.freeze('A', [obs('T', 1, x=1)])
        with self.assertRaises(ValueError):
            self.freeze('A', [obs('T', 7, x=1), bad_row], previous=original.revision_id)
        self.close_sources()
        self.open_sources()
        store = self.revisions['A']
        self.assertEqual(store.list_revisions('A', 'R'), (original.revision_id,))
        self.assertEqual(store.get(original.revision_id), original)
        with self.assertRaises(KeyError):
            store.get(original.revision_id + 1)

    def test_unknown_batch_rejects_all_rows(self):
        self.assert_rejected_batch(obs('unknown', 2, y=1))

    def test_bad_rational_rejects_all_rows(self):
        self.assert_rejected_batch(obs('T', '1/0', y=1))

    def test_bad_unit_rejects_all_rows(self):
        self.assert_rejected_batch(obs('T', 3, unit='seconds', y=1))

    def test_missing_field_and_nonexact_coefficients_reject(self):
        self.catalog.register('R', [batch('T')])
        missing_unit = obs('T', 1, x=1)
        del missing_unit['unit']
        for row in (missing_unit, obs('T', 1, x=True), obs('T', 1, x=0.1)):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.freeze('A', [row])
        self.assertEqual(self.revisions['A'].list_revisions('A', 'R'), ())
        self.close_sources()
        with self.assertRaises(sqlite3.ProgrammingError):
            self.catalog.get('R')
