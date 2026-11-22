import hashlib
import json
from contextlib import ExitStack
from fractions import Fraction

from drift_workday import freeze_workday, interrupt_receipt, load_workday
from evidence.issue import issue_drift
from publication.export import export_report
from publication.history import read
from publication.receipts import canonical_json
from publication.sign import sign, sign_drift
from review.intake import receive, receive_drift
from review.joint import assess
from tests import LabCase, batch, obs


class DriftWorkdayCase(LabCase):
    def open_workday(self, name='crossed'):
        sample = load_workday(name)
        stack = ExitStack()
        self.addCleanup(stack.close)
        catalog, stations, frozen = freeze_workday(stack, sample, self.connect)
        return sample, stack, catalog, stations, frozen

    def issue_received(self, catalog, stations, revision, work_box, certified_bounds):
        text = issue_drift(catalog, stations[revision.station], revision.revision_id,
                           work_box, certified_bounds)
        return text, receive_drift(self.intake, text)

    def crossed_pieces(self):
        sample, stack, catalog, stations, frozen = self.open_workday('crossed')
        received = {}
        for label, revision in frozen.items():
            _, received[label] = self.issue_received(
                catalog, stations, revision, sample['work_box'],
                sample['versions'][label]['certified_bounds'])
        return sample, stack, received

    def simple_pair(self, left, right, box, left_bounds=None, right_bounds=None, run='R'):
        self.catalog.register(run, [batch('T')])
        a = self.freeze('A', left, run=run)
        b = self.freeze('B', right, run=run)
        a_in = self.issue_received(self.catalog, self.revisions, a, box, left_bounds or {})[1]
        b_in = self.issue_received(self.catalog, self.revisions, b, box, right_bounds or {})[1]
        self.close_sources()
        return a_in, b_in


class DriftSignTests(DriftWorkdayCase):
    def test_crossed_window_table(self):
        sample, stack, received = self.crossed_pieces()
        stack.close()
        expectations = {
            ('b', 'full'): [{'excluded_batch': None, 'range': ['1', '1']}],
            ('b', 'early'): [],
            ('b', 'point'): [{'excluded_batch': None, 'range': ['1', '1']}],
            ('b_corrected', 'full'): [{'excluded_batch': None, 'range': ['0', '2']}],
            ('b_corrected', 'early'): [{'excluded_batch': None, 'range': ['3/2', '2']}],
            ('b_corrected', 'point'): [{'excluded_batch': None, 'range': ['1', '1']}],
        }
        expected_windows = {'full': ['0', '2'], 'early': ['0', '1/2'], 'point': ['1', '1']}
        for (right, window), expected in expectations.items():
            with self.subTest(right=right, window=window):
                report = sign_drift(self.publication, self.intake,
                                    received['a'].key, received[right].key,
                                    sample['windows'][window], sample['contrast'])
                self.assertEqual(report.body['cases'], expected)
                self.assertEqual(report.body['kind'], 'drift')
                self.assertEqual(report.body['work_box'],
                                 {'x': ['0', '2'], 'y': ['0', '0'], 'z': ['0', '2']})
                self.assertEqual(report.body['window'], expected_windows[window])
                self.assertEqual(report.body['contrast'], ['1', '0'])
                self.assertEqual(report.parents, (received['a'].key, received[right].key))
                self.assertEqual(read(self.publication, report.number), report)

    def test_wider_a_bounds_reissue_keeps_first_intake(self):
        sample, stack, catalog, stations, frozen = self.open_workday('crossed')
        received = {}
        for label, revision in frozen.items():
            _, received[label] = self.issue_received(
                catalog, stations, revision, sample['work_box'],
                sample['versions'][label]['certified_bounds'])
        wider_text, wider = self.issue_received(catalog, stations, frozen['a'],
                                                sample['work_box'], sample['wider_a_bounds'])
        original_text = issue_drift(catalog, stations['A'], frozen['a'].revision_id,
                                    sample['work_box'], sample['versions']['a']['certified_bounds'])
        stack.close()
        self.assertNotEqual(wider.key, received['a'].key)
        self.assertEqual(receive_drift(self.intake, wider_text).key, wider.key)
        self.assertEqual(receive_drift(self.intake, original_text).key, received['a'].key)
        report = sign_drift(self.publication, self.intake, wider.key, received['b'].key,
                            sample['windows']['full'], sample['contrast'])
        self.assertEqual(report.body['cases'], [{'excluded_batch': None, 'range': ['1/2', '3/2']}])
        original = sign_drift(self.publication, self.intake, received['a'].key, received['b'].key,
                              sample['windows']['full'], sample['contrast'])
        self.assertEqual(original.body['cases'], [{'excluded_batch': None, 'range': ['1', '1']}])

    def test_global_scope_only_dropping_g_signs(self):
        sample, stack, catalog, stations, frozen = self.open_workday('global_scope')
        received = {}
        for label, revision in frozen.items():
            _, received[label] = self.issue_received(
                catalog, stations, revision, sample['work_box'],
                sample['versions'][label]['certified_bounds'])
        stack.close()
        report = sign_drift(self.publication, self.intake, received['a'].key, received['b'].key,
                            sample['windows']['full'], sample['contrast'])
        self.assertEqual(report.body['cases'], [{'excluded_batch': 'G', 'range': ['1', '1']}])

    def test_double_offset_correlation(self):
        box = {'x': [0, 2], 'y': [-1, 1], 'z': [0, 2]}
        a_in, b_in = self.simple_pair(
            [obs('T', 0, x=1, ref_shift=1, u=-1, v=-1), obs('T', 0, y=1, u=-1, v=1)],
            [obs('T', 0, x=1, ref_shift=-1), obs('T', '1/2', y=1)],
            box, {'u': [0, 1], 'v': [0, 1]}, {})
        report = sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 2], [1, 0])
        self.assertEqual(report.body['cases'], [{'excluded_batch': None, 'range': ['1/4', '3/4']}])

    def test_zero_contrast_on_feasible_case(self):
        box = {'x': [0, 2], 'y': [0, 3], 'z': [0, 0]}
        a_in, b_in = self.simple_pair([obs('T', 1, x=1)], [obs('T', 2, y=1)], box)
        report = sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 0], (0, 0))
        self.assertEqual(report.body['cases'], [{'excluded_batch': None, 'range': ['0', '0']}])

    def test_all_infeasible_signs_empty_cases(self):
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        a_in, b_in = self.simple_pair([obs('T', 1, x=1)], [obs('T', 2, x=1)], box)
        report = sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 2], [1, 0])
        self.assertEqual(report.body['cases'], [])
        self.assertEqual(read(self.publication, report.number).body['cases'], [])

    def test_station_side_infeasible_skips_case(self):
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        a_in, b_in = self.simple_pair([obs('T', 1, x=1), obs('T', 2, x=1)], [obs('T', 3, y=1)], box)
        report = sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 2], [1, 0])
        self.assertEqual(report.body['cases'], [])

    def test_empty_observation_set_spans_the_box(self):
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        a_in, b_in = self.simple_pair([], [], box)
        report = sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 2], [1, 1])
        self.assertEqual(report.body['cases'], [{'excluded_batch': None, 'range': ['0', '4']}])

    def test_certified_bound_interacts_with_exclusion(self):
        self.catalog.register('R', [batch('T'), batch('G', 'candidate')])
        a = self.freeze('A', [obs('T', 1, x=1), obs('G', 1, t=1)])
        b = self.freeze('B', [obs('T', 2, y=1)])
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        a_in = self.issue_received(self.catalog, self.revisions, a, box, {'t': [0, 0]})[1]
        b_in = self.issue_received(self.catalog, self.revisions, b, box, {})[1]
        self.close_sources()
        report = sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 2], [1, 0])
        self.assertEqual(report.body['cases'], [{'excluded_batch': 'G', 'range': ['1', '1']}])

    def test_issue_is_deterministic_per_inputs(self):
        self.catalog.register('R', [batch('T')])
        a = self.freeze('A', [obs('T', 1, x=1, t=1)])
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        first = issue_drift(self.catalog, self.revisions['A'], a.revision_id, box, {'t': [0, 1]})
        second = issue_drift(self.catalog, self.revisions['A'], a.revision_id, box, {'t': [0, 1]})
        self.assertEqual(first, second)

    def test_exclusion_case_order_and_trusted_rows(self):
        self.catalog.register('R', [batch('T'), batch('H', 'candidate'), batch('G', 'candidate')])
        a = self.freeze('A', [obs('T', 1, x=1), obs('G', 0, t=1)])
        b = self.freeze('B', [obs('T', 2, y=1), obs('H', 0, s=1)])
        box = {'x': [0, 9], 'y': [0, 9], 'z': [0, 0]}
        a_in = self.issue_received(self.catalog, self.revisions, a, box, {})[1]
        b_in = self.issue_received(self.catalog, self.revisions, b, box, {})[1]
        self.close_sources()
        report = sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 0], [1, 1])
        self.assertEqual(report.body['cases'], [
            {'excluded_batch': None, 'range': ['3', '3']},
            {'excluded_batch': 'H', 'range': ['3', '3']},
            {'excluded_batch': 'G', 'range': ['3', '3']},
        ])

    def test_report_commit_is_atomic_and_retryable(self):
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        a_in, b_in = self.simple_pair([obs('T', 1, x=1)], [obs('T', 2, y=1)], box)
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 2], [1, 0],
                       after_body=interrupt_receipt)
        self.assertEqual(self.publication_counts(), (0, 0, 0))
        report = sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 2], [1, 0])
        self.assertEqual(self.publication_counts(), (1, 2, 1))
        self.assertEqual(read(self.publication, report.number), report)

    def test_history_and_export_after_reopening(self):
        sample, stack, received = self.crossed_pieces()
        stack.close()
        full = sign_drift(self.publication, self.intake, received['a'].key, received['b'].key,
                          sample['windows']['full'], sample['contrast'])
        early = sign_drift(self.publication, self.intake, received['a'].key,
                           received['b_corrected'].key, sample['windows']['early'], sample['contrast'])
        self.centre.close()
        self.open_centre()
        self.assertEqual(read(self.publication, full.number), full)
        self.assertEqual(read(self.publication, early.number), early)
        with self.assertRaises(KeyError):
            read(self.publication, early.number + 1)
        destination = self.root / 'drift-report.json'
        export_report(self.publication, full.number, destination)
        exported = json.loads(destination.read_text(encoding='utf-8'))
        self.assertEqual(exported['body'], full.body)
        self.assertEqual(exported['parents'], list(full.parents))
        self.assertEqual(exported['receipt'], full.receipt.document())


class DriftIntakeTests(DriftWorkdayCase):
    def test_rereceive_same_text_returns_first_key(self):
        sample, stack, catalog, stations, frozen = self.open_workday('crossed')
        text = issue_drift(catalog, stations['A'], frozen['a'].revision_id,
                           sample['work_box'], sample['versions']['a']['certified_bounds'])
        stack.close()
        first = receive_drift(self.intake, text)
        self.assertEqual(receive_drift(self.intake, text).key, first.key)
        document = json.loads(text)
        shuffled = json.dumps({key: document[key] for key in reversed(list(document))},
                              ensure_ascii=False, indent=2)
        self.assertEqual(receive_drift(self.intake, shuffled).key, first.key)
        self.assertEqual(self.intake.get_drift(first.key), first)

    def test_piece_structure_and_checksum(self):
        sample, stack, catalog, stations, frozen = self.open_workday('crossed')
        text = issue_drift(catalog, stations['A'], frozen['a'].revision_id,
                           sample['work_box'], sample['versions']['a']['certified_bounds'])
        stack.close()
        document = json.loads(text)
        self.assertEqual(set(document), {'version', 'run_id', 'station', 'revision_id',
                                         'roster_digest', 'work_box', 'cases', 'checksum'})
        self.assertEqual(document['version'], 2)
        self.assertEqual(document['station'], 'A')
        self.assertIsNone(document['cases'][0]['excluded_batch'])
        body = {key: value for key, value in document.items() if key != 'checksum'}
        digest = hashlib.sha256(canonical_json(body).encode('utf-8')).hexdigest()
        self.assertEqual(document['checksum'], digest)
        self.assertNotIn('reading', text)
        self.assertNotIn('coefficients', text)

    def test_private_symbols_stay_on_site(self):
        self.catalog.register('R', [batch('T')])
        a = self.freeze('A', [obs('T', 5, private_offset_87=1, x=1),
                              obs('T', 4, private_offset_87=1)])
        text = issue_drift(self.catalog, self.revisions['A'], a.revision_id,
                           {'x': [0, 9], 'y': [0, 9], 'z': [0, 9]}, {'private_offset_87': [0, 9]})
        self.assertNotIn('private_offset_87', text)
        self.assertNotIn('reading', text)
        self.assertNotIn('coefficients', text)

    def test_damaged_and_crafted_pieces_reject(self):
        sample, stack, catalog, stations, frozen = self.open_workday('crossed')
        text = issue_drift(catalog, stations['A'], frozen['a'].revision_id,
                           sample['work_box'], sample['versions']['a']['certified_bounds'])
        stack.close()
        document = json.loads(text)
        tampered = dict(document, checksum='0' * 64)
        with self.assertRaises(ValueError):
            receive_drift(self.intake, json.dumps(tampered))
        duplicated = text.replace('"version":2', '"version":2,"version":2', 1)
        with self.assertRaises(ValueError):
            receive_drift(self.intake, duplicated)
        with self.assertRaises(ValueError):
            receive_drift(self.intake, json.dumps(dict(document, extra=1)))
        with self.assertRaises(ValueError):
            receive_drift(self.intake, json.dumps(dict(document, version=1)))
        with self.assertRaises(ValueError):
            receive_drift(self.intake, json.dumps(dict(document, station='C')))
        crafted = json.loads(text)
        crafted['cases'][0]['relation']['inequalities'][0][-1] = '2/4'
        with self.assertRaises(ValueError):
            receive_drift(self.intake, json.dumps(crafted))
        nonnormalized = json.loads(text)
        relation = nonnormalized['cases'][0]['relation']
        relation['inequalities'] = [[str(2 * Fraction(cell)) for cell in row]
                                    for row in relation['inequalities']]
        body = {key: value for key, value in nonnormalized.items() if key != 'checksum'}
        nonnormalized['checksum'] = hashlib.sha256(
            canonical_json(body).encode('utf-8')).hexdigest()
        with self.assertRaises(ValueError):
            receive_drift(self.intake, json.dumps(nonnormalized))
        self.assertEqual(receive_drift(self.intake, text).key, document['checksum'])

    def test_v1_and_drift_pieces_do_not_mix(self):
        self.catalog.register('R', [batch('T')])
        a, b = self.freeze_pair([obs('T', 1, x=1)], [obs('T', 2, y=1)])
        v1_a, v1_b = (self.deliver(revision) for revision in (a, b))
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        drift_a_text, drift_a = self.issue_received(self.catalog, self.revisions, a, box, {})
        _, drift_b = self.issue_received(self.catalog, self.revisions, b, box, {})
        self.close_sources()
        with self.assertRaises(ValueError):
            receive_drift(self.intake, self.root / 'not-a-string')
        v1_text = (self.root / f'{v1_a.piece.piece_id}.json').read_text(encoding='utf-8')
        with self.assertRaises(ValueError):
            receive_drift(self.intake, v1_text)
        with self.assertRaises(ValueError):
            receive(self.intake, drift_a_text)
        with self.assertRaises(ValueError):
            sign_drift(self.publication, self.intake, v1_a.key, v1_b.key, [0, 2], [1, 0])
        with self.assertRaises(ValueError):
            assess(self.intake, drift_a.key, drift_b.key, (1, 0), (0, 0))
        with self.assertRaises(ValueError):
            assess(self.intake, drift_a.key, v1_b.key, (1, 0), (0, 0))
        result = assess(self.intake, v1_a.key, v1_b.key, (1, 1), (1, 2))
        self.assertEqual(sign(self.publication, self.intake, result).body['cases'][0]
                         ['contrast'], {'kind': 'fixed', 'value': '3'})
        report = sign_drift(self.publication, self.intake, drift_a.key, drift_b.key, [0, 2], [1, 0])
        self.assertEqual(report.body['cases'], [{'excluded_batch': None, 'range': ['1', '1']}])

    def test_unknown_and_malformed_keys(self):
        sample, stack, received = self.crossed_pieces()
        stack.close()
        with self.assertRaises(KeyError):
            sign_drift(self.publication, self.intake, received['a'].key, 'f' * 64,
                       sample['windows']['full'], sample['contrast'])
        with self.assertRaises(ValueError):
            sign_drift(self.publication, self.intake, received['a'].key, 'not-hex',
                       sample['windows']['full'], sample['contrast'])
        with self.assertRaises(KeyError):
            self.intake.get_drift('f' * 64)


class DriftValidationTests(DriftWorkdayCase):
    def open_revision(self):
        self.catalog.register('R', [batch('T')])
        return self.freeze('A', [obs('T', 1, x=1, t=1)])

    def test_work_box_validation(self):
        revision = self.open_revision()
        for bad_box in ({'x': [0, 2], 'y': [0, 2]},
                        {'x': [0, 2], 'y': [0, 2], 'z': [0, 2], 'w': [0, 1]},
                        {'x': [2, 0], 'y': [0, 2], 'z': [0, 2]},
                        {'x': [0, 2, 3], 'y': [0, 2], 'z': [0, 2]},
                        {'x': [0, '1/0'], 'y': [0, 2], 'z': [0, 2]},
                        ['x', 'y', 'z']):
            with self.subTest(box=bad_box), self.assertRaises(ValueError):
                issue_drift(self.catalog, self.revisions['A'], revision.revision_id, bad_box, {})

    def test_certified_bounds_validation(self):
        revision = self.open_revision()
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        for bad_bounds in ({'x': [0, 1]}, {'y': [0, 1]}, {'ref_shift': [0, 1]},
                           {'t': [0, 1], 'u': [0, 1], 'v': [0, 1]},
                           {'t': [1, 0]}, {'not an id': [0, 1]}, {1: [0, 1]},
                           {'t': [0]}, {'t': [0, '1/0']}, 't'):
            with self.subTest(bounds=bad_bounds), self.assertRaises(ValueError):
                issue_drift(self.catalog, self.revisions['A'], revision.revision_id,
                            box, bad_bounds)

    def test_unknown_revision_and_bad_id(self):
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        self.catalog.register('R', [batch('T')])
        with self.assertRaises(KeyError):
            issue_drift(self.catalog, self.revisions['A'], 99, box, {})
        with self.assertRaises(ValueError):
            issue_drift(self.catalog, self.revisions['A'], 'soon', box, {})

    def test_window_and_contrast_validation(self):
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        a_in, b_in = self.simple_pair([obs('T', 1, x=1)], [obs('T', 2, y=1)], box)
        for bad_window in ([3, 4], [2, 1], [0], [0, 2, 3], ['1/0', 2], [True, 2], 'full'):
            with self.subTest(window=bad_window), self.assertRaises(ValueError):
                sign_drift(self.publication, self.intake, a_in.key, b_in.key, bad_window, [1, 0])
        for bad_contrast in ([1], [1, 0, 0], ['1/0', 0], [True, 0], 'x'):
            with self.subTest(contrast=bad_contrast), self.assertRaises(ValueError):
                sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 2], bad_contrast)
        self.assertEqual(self.publication_counts(), (0, 0, 0))

    def test_parent_mismatches_reject(self):
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        other_box = {'x': [0, 3], 'y': [0, 2], 'z': [0, 2]}
        self.catalog.register('R', [batch('T')])
        self.catalog.register('Q', [batch('T')])
        a = self.freeze('A', [obs('T', 1, x=1)])
        a2 = self.freeze('A', [obs('T', 1, x=1)], run='Q')
        b = self.freeze('B', [obs('T', 2, y=1)])
        b_wide = self.freeze('B', [obs('T', 2, y=1)])
        b_q = self.freeze('B', [obs('T', 2, y=1)], run='Q')
        a_in = self.issue_received(self.catalog, self.revisions, a, box, {})[1]
        a2_in = self.issue_received(self.catalog, self.revisions, a2, box, {})[1]
        b_in = self.issue_received(self.catalog, self.revisions, b, box, {})[1]
        b_wide_in = self.issue_received(self.catalog, self.revisions, b_wide, other_box, {})[1]
        b_q_in = self.issue_received(self.catalog, self.revisions, b_q, box, {})[1]
        self.close_sources()
        with self.assertRaises(ValueError):
            sign_drift(self.publication, self.intake, a_in.key, a2_in.key, [0, 2], [1, 0])
        with self.assertRaises(ValueError):
            sign_drift(self.publication, self.intake, b_in.key, a_in.key, [0, 2], [1, 0])
        with self.assertRaises(ValueError):
            sign_drift(self.publication, self.intake, a_in.key, b_wide_in.key, [0, 2], [1, 0])
        with self.assertRaises(ValueError):
            sign_drift(self.publication, self.intake, a_in.key, b_q_in.key, [0, 2], [1, 0])
        self.assertEqual(self.publication_counts(), (0, 0, 0))

    def test_different_roster_scope_rejects(self):
        self.catalog.register('R', [batch('T')])
        self.catalog.register('S', [batch('T'), batch('G', 'candidate')])
        box = {'x': [0, 2], 'y': [0, 2], 'z': [0, 2]}
        a = self.freeze('A', [obs('T', 1, x=1)])
        b = self.freeze('B', [obs('T', 2, y=1)], run='S')
        a_in = self.issue_received(self.catalog, self.revisions, a, box, {})[1]
        b_in = self.issue_received(self.catalog, self.revisions, b, box, {})[1]
        self.close_sources()
        with self.assertRaises(ValueError):
            sign_drift(self.publication, self.intake, a_in.key, b_in.key, [0, 2], [1, 0])
