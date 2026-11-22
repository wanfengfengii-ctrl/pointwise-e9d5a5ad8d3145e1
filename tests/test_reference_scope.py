import json

from publication.history import read
from publication.sign import sign
from review.joint import assess
from tests import LabCase, batch, obs


class ReferenceScopeTests(LabCase):
    def review(self, left, right, contrast, claim, order=('G', 'H', 'K')):
        self.catalog.register('R', [batch('T'), *(batch(key, 'candidate') for key in order)])
        received = tuple(self.deliver(revision) for revision in self.freeze_pair(left, right))
        self.close_sources()
        keys = tuple(entry.key for entry in received)
        result = assess(self.intake, *keys, contrast, claim)
        signed = sign(self.publication, self.intake, result)
        saved = read(self.publication, signed.number)
        self.assertEqual(saved.parents, keys)
        self.assertEqual(saved.parent_checksums, tuple(entry.piece.checksum for entry in received))
        self.assertEqual(saved.receipt.parent_checksums, saved.parent_checksums)
        self.assertEqual(saved, signed)
        return result, saved

    def test_global_scope(self):
        left = [obs('G', 1, x=1), obs('H', 2, x=1)]
        right = [obs('G', 1, y=1), obs('K', 2, y=1)]
        result, saved = self.review(left, right, (1, 1), (1, 2))
        expected = [{'excluded_batch': 'G', 'contrast': {'kind': 'fixed', 'value': '4'},
                     'supports_claim': False}]
        actual = [{'excluded_batch': finding.excluded_batch,
                   'contrast': {'kind': finding.contrast.kind, 'value': str(finding.contrast.value)},
                   'supports_claim': finding.supports_claim} for finding in result.findings]
        self.assertEqual(actual, expected)
        self.assertEqual(result.supporting_cases, ())
        self.assertEqual(saved.body['cases'], expected)
        self.assertEqual(saved.body['supporting_cases'], [])
        self.assertFalse(saved.body['supported'])
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'T6.global_scope',
            'input': {'A': left, 'B': right, 'contrast': [1, 1], 'claim': [1, 2]},
            'expected': expected, 'actual': actual,
            'downstream_expected': {'cases': expected, 'supporting_cases': []},
            'downstream_actual': {'cases': saved.body['cases'], 'supporting_cases': saved.body['supporting_cases']},
            'code_paths': ['evidence/issue.py', 'review/joint.py', 'publication/sign.py', 'publication/history.py'],
            'oracle': 'Only dropping G lets each station retain its second equality. Both coordinates are then 2.'
        }, ensure_ascii=False, sort_keys=True))

    def test_shared_offset(self):
        left = [obs('G', 0, t=1), obs('H', 2, x=1, t=1)]
        right = [obs('G', 0, s=1), obs('K', 3, x=1, s=1)]
        result, saved = self.review(left, right, (1, 0), (4, 0))
        self.assertEqual([(case.excluded_batch, case.contrast.value) for case in result.findings],
                         [('G', None), ('H', 3), ('K', 2)])
        self.assertEqual(result.supporting_cases, ('G',))
        self.assertEqual(saved.body['cases'], [
            {'excluded_batch': 'G', 'contrast': {'kind': 'all_rationals'}, 'supports_claim': True},
            {'excluded_batch': 'H', 'contrast': {'kind': 'fixed', 'value': '3'}, 'supports_claim': False},
            {'excluded_batch': 'K', 'contrast': {'kind': 'fixed', 'value': '2'}, 'supports_claim': False},
        ])
        self.assertEqual(saved.body['supporting_cases'], ['G'])

    def test_alternate_support(self):
        left = [obs('G', 0, t=1), obs('H', 2, x=1, t=1), obs('T', 2, x=1)]
        right = [obs('G', 0, s=1), obs('K', 3, x=1, s=1)]
        result, saved = self.review(left, right, (1, 0), (2, 0))
        self.assertEqual([(case.excluded_batch, case.contrast.value) for case in result.findings],
                         [('G', 2), ('K', 2)])
        self.assertEqual(result.supporting_cases, ('G', 'K'))
        self.assertEqual(saved.body['cases'][0]['contrast'], {'kind': 'fixed', 'value': '2'})
        self.assertEqual(saved.body['supporting_cases'], ['G', 'K'])

    def test_registration_order_and_absent_candidate_rows(self):
        left = [obs('T', 1, x=1)]
        right = [obs('T', 2, y=1), obs('H', 2, y=1), obs('H', 2, y=1)]
        result, saved = self.review(left, right, (1, 1), (1, 2), order=('K', 'H', 'G'))
        self.assertEqual([(case.excluded_batch, case.contrast.value) for case in result.findings],
                         [(None, 3), ('K', 3), ('H', 3), ('G', 3)])
        self.assertEqual(saved.body['supporting_cases'], [None, 'K', 'H', 'G'])

    def test_exclusion_removes_all_rows_of_the_batch(self):
        left = [obs('G', 1, x=1), obs('G', 0, y=1), obs('H', 2, x=1)]
        right = [obs('G', 7, x=1), obs('K', 3, y=1)]
        result, saved = self.review(left, right, (1, 1), (2, 3))
        self.assertEqual([(case.excluded_batch, case.contrast.value) for case in result.findings], [('G', 5)])
        self.assertEqual(saved.body['supporting_cases'], ['G'])
