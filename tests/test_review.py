import json
from fractions import Fraction

from evidence.envelope import encode_envelope, seal_envelope
from evidence.relations import AffineRelation
from publication.history import read
from publication.sign import sign
from review.intake import receive
from review.joint import assess
from tests import LabCase, batch, obs


class ReviewTests(LabCase):
    def offline_parents(self, left, right):
        self.catalog.register('R', [batch('T')])
        parents = tuple(self.deliver(revision) for revision in self.freeze_pair(left, right))
        self.close_sources()
        return tuple(parent.key for parent in parents)

    def test_ordinary_offline_signature(self):
        keys = self.offline_parents([obs('T', 1, x=1)], [obs('T', 2, y=1)])
        result = assess(self.intake, *keys, (1, 1), (1, 2))
        signed = sign(self.publication, self.intake, result)
        self.assertEqual(signed.body['cases'], [
            {'excluded_batch': None, 'contrast': {'kind': 'fixed', 'value': '3'}, 'supports_claim': True}
        ])
        self.assertEqual(signed.body['supporting_cases'], [None])
        self.assertEqual(signed.parents, keys)
        self.assertEqual(signed.receipt.parent_ids, keys)
        self.assertEqual(read(self.publication, signed.number), signed)

    def test_fixed_contrast_with_free_coordinates(self):
        keys = self.offline_parents([obs('T', '3/1000', unit='mm', x=1, y=1)], [obs('T', 8, s=1)])
        for contrast in ((1, 0), (0, 1)):
            self.assertIsNone(assess(self.intake, *keys, contrast, (1, 2)).findings[0].contrast.value)
        result = assess(self.intake, *keys, (1, 1), (1, 2))
        self.assertEqual(result.findings[0].contrast.value, Fraction(3))
        signed = sign(self.publication, self.intake, result)
        self.assertEqual(read(self.publication, signed.number).body['cases'][0]['contrast'],
                         {'kind': 'fixed', 'value': '3'})

    def test_pair_support_and_zero_contrast(self):
        keys = self.offline_parents([obs('T', 3, x=1, y=1)], [obs('T', 8, s=1)])
        supported = assess(self.intake, *keys, (0, 0), (1, 2))
        rejected = assess(self.intake, *keys, (0, 0), (1, 3))
        self.assertEqual(supported.supporting_cases, (None,))
        self.assertEqual(rejected.supporting_cases, ())
        self.assertEqual(rejected.findings[0].contrast.value, 0)
        self.assertFalse(sign(self.publication, self.intake, rejected).body['supported'])

    def test_mixed_runs_with_same_batch_id_reject(self):
        self.catalog.register('R', [batch('G', 'candidate')])
        self.catalog.register('Q', [batch('G', 'candidate')])
        a = self.deliver(self.freeze('A', [obs('G', 1, x=1)]))
        b = self.deliver(self.freeze('B', [obs('G', 2, y=1)], run='Q'))
        self.close_sources()
        with self.assertRaises(ValueError):
            assess(self.intake, a.key, b.key, (1, 1), (1, 2))
        self.assertEqual(self.publication_counts(), (0, 0, 0))

    def test_envelope_conflict(self):
        self.catalog.register('R', [batch('T')])
        a, b = self.freeze_pair([obs('T', 1, x=1)], [obs('T', 2, y=1)])
        received = self.deliver(a)
        b_received = self.deliver(b)
        original = received.piece
        damaged = json.loads(encode_envelope(original))
        damaged['cases'][0]['equations'][0][-1] = '17'
        with self.assertRaises(ValueError):
            receive(self.intake, json.dumps(damaged))
        conflict = seal_envelope(original.run_id, original.station, original.revision_id,
                                 original.roster_digest, ((None, AffineRelation.from_rows(((1, 0, 17),))),))
        self.assertEqual(conflict.piece_id, original.piece_id)
        self.assertNotEqual(conflict.checksum, original.checksum)
        with self.assertRaises(ValueError):
            receive(self.intake, conflict)
        self.close_sources()
        self.assertEqual(self.intake.get(received.key), received)
        result = assess(self.intake, received.key, b_received.key, (1, 1), (1, 2))
        self.assertEqual(result.findings[0].contrast.value, 3)
        self.assertTrue(result.supported)

    def test_wrong_station_missing_parent_and_invalid_requests(self):
        self.catalog.register('R', [batch('T')])
        a = self.freeze('A', [obs('T', 1, x=1)])
        a_next = self.freeze('A', [obs('T', 3, x=1)], previous=a.revision_id)
        b = self.freeze('B', [obs('T', 2, y=1)])
        first, second, right = (self.deliver(revision) for revision in (a, a_next, b))
        self.close_sources()
        with self.assertRaises(ValueError):
            assess(self.intake, first.key, second.key, (1, 1), (1, 2))
        with self.assertRaises(KeyError):
            assess(self.intake, first.key, 'f' * 64, (1, 1), (1, 2))
        for contrast, claim in (((1,), (1, 2)), ((1, 1), ('1/0', 2)), ((True, 1), (1, 2))):
            with self.subTest(contrast=contrast, claim=claim), self.assertRaises(ValueError):
                assess(self.intake, first.key, right.key, contrast, claim)
        self.assertEqual(self.publication_counts(), (0, 0, 0))

    def test_same_run_with_different_roster_digest_rejects(self):
        self.catalog.register('R', [batch('T'), batch('G', 'candidate')])
        a, b = self.freeze_pair([obs('T', 1, x=1)], [obs('T', 2, y=1)])
        left = self.deliver(a)
        right = self.issue(b)
        other = seal_envelope(right.run_id, right.station, right.revision_id, '1' * 64, right.cases)
        received = receive(self.intake, other)
        self.close_sources()
        with self.assertRaises(ValueError):
            assess(self.intake, left.key, received.key, (1, 1), (1, 2))
        self.assertEqual(self.publication_counts(), (0, 0, 0))

    def test_no_common_solution_still_signs_empty_result(self):
        keys = self.offline_parents([obs('T', 1, x=1)], [obs('T', 2, x=1)])
        result = assess(self.intake, *keys, (1, 0), (1, 0))
        self.assertEqual(result.findings, ())
        stored = sign(self.publication, self.intake, result)
        self.assertEqual(stored.body['cases'], [])
        self.assertEqual(stored.body['supporting_cases'], [])
        self.assertFalse(stored.body['supported'])
        self.assertEqual(read(self.publication, stored.number).parents, keys)
