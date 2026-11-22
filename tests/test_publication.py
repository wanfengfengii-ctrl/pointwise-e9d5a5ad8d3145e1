import hashlib
import json
import sqlite3
from dataclasses import replace

from publication.history import read
from publication.sign import sign
from review.joint import assess
from tests import LabCase, batch, obs


class PublicationTests(LabCase):
    def offline_result(self):
        self.catalog.register('R', [batch('T')])
        a, b = (self.deliver(revision) for revision in
                self.freeze_pair([obs('T', 1, x=1)], [obs('T', 2, y=1)]))
        self.close_sources()
        return assess(self.intake, a.key, b.key, (1, 1), (1, 2))

    def test_retry_commit(self):
        result = self.offline_result()
        attempted_numbers = []

        def interrupt():
            self.assertEqual(self.publication_counts(), (1, 2, 0))
            attempted_numbers.append(self.centre.execute('SELECT number FROM reports').fetchone()[0])
            raise OSError('publication interrupted before receipt')

        with self.assertRaisesRegex(OSError, 'before receipt'):
            sign(self.publication, self.intake, result, after_body=interrupt)
        self.assertEqual(len(attempted_numbers), 1)
        self.centre.close()
        self.open_centre()
        self.assertEqual(self.publication_counts(), (0, 0, 0))
        with self.assertRaises(KeyError):
            read(self.publication, attempted_numbers[0])
        signed = sign(self.publication, self.intake, result)
        self.assertEqual(self.publication_counts(), (1, 2, 1))
        earned = read(self.publication, signed.number)
        self.assertEqual(earned, signed)
        self.assertEqual(earned.receipt.report_number, earned.number)
        self.assertEqual(earned.receipt.parent_ids, result.parents)
        expected_bytes = json.dumps(earned.body, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')
        self.assertEqual(earned.receipt.body_checksum, hashlib.sha256(expected_bytes).hexdigest())

    def test_sqlite_receipt_failure_preserves_earlier_signed_report(self):
        result = self.offline_result()
        first = sign(self.publication, self.intake, result)
        self.centre.execute('''
            CREATE TEMP TRIGGER fail_receipt BEFORE INSERT ON receipts
            BEGIN SELECT RAISE(ABORT, 'receipt unavailable'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt unavailable'):
            sign(self.publication, self.intake, result)
        self.centre.close()
        self.open_centre()
        self.assertEqual(self.publication_counts(), (1, 2, 1))
        self.assertEqual(read(self.publication, first.number), first)
        second = sign(self.publication, self.intake, result)
        self.assertNotEqual(first.number, second.number)
        self.assertEqual(self.publication_counts(), (2, 4, 2))

    def test_sign_rejects_parent_mismatch_and_duplicate_case(self):
        result = self.offline_result()
        wrong_parent = replace(result, parent_checksums=('0' * 64, result.parent_checksums[1]))
        duplicate_case = replace(result, findings=result.findings * 2)
        for invalid in (wrong_parent, duplicate_case):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                sign(self.publication, self.intake, invalid)
        self.assertEqual(self.publication_counts(), (0, 0, 0))
