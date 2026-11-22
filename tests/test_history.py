import json

from publication.export import export_report
from publication.history import read
from publication.sign import sign
from review.joint import assess
from tests import LabCase, batch, obs


class HistoryTests(LabCase):
    def record_correction(self):
        self.roster = self.catalog.register('R', [batch('T')])
        self.a, self.b = self.freeze_pair([obs('T', 1, x=1)], [obs('T', 2, y=1)])
        self.a_in, self.b_in = self.deliver(self.a), self.deliver(self.b)
        self.close_sources()
        old_result = assess(self.intake, self.a_in.key, self.b_in.key, (1, 1), (1, 2))
        self.old = sign(self.publication, self.intake, old_result)
        self.open_sources()
        self.b_next = self.freeze('B', [obs('T', 5, y=1)], previous=self.b.revision_id)
        self.b_next_in = self.deliver(self.b_next)
        self.close_sources()
        new_result = assess(self.intake, self.a_in.key, self.b_next_in.key, (1, 1), (1, 5))
        self.new = sign(self.publication, self.intake, new_result)

    def test_successor_preserves_previous_revision(self):
        self.record_correction()
        self.open_sources()
        store = self.revisions['B']
        self.assertEqual(store.list_revisions('B', 'R'), (self.b.revision_id, self.b_next.revision_id))
        original = store.get(self.b.revision_id)
        successor = store.get(self.b_next.revision_id)
        self.assertEqual(successor.previous, original.revision_id)
        self.assertEqual(original, self.b)
        self.assertEqual(original.original_rows, [obs('T', 2, y=1)])
        self.assertEqual(successor.original_rows, [obs('T', 5, y=1)])
        self.catalog.register('Q', [batch('T')])
        with self.assertRaises(ValueError):
            self.freeze('B', [obs('T', 5, y=1)], run='Q', previous=original.revision_id)
        self.assertEqual(store.list_revisions('B', 'Q'), ())

    def test_issue_pinned_after_correction(self):
        self.record_correction()
        self.open_sources()
        pinned = self.deliver(self.b)
        self.assertEqual(pinned, self.b_in)
        self.assertNotEqual(pinned.key, self.b_next_in.key)
        self.close_sources()
        old_result = assess(self.intake, self.a_in.key, pinned.key, (1, 1), (1, 2))
        self.assertEqual(old_result.findings[0].contrast.value, 3)
        self.assertEqual(old_result.parents, self.old.parents)
        self.assertEqual(self.new.body['cases'][0]['contrast']['value'], '6')

    def test_read_original_after_reopening(self):
        self.record_correction()
        self.centre.close()
        self.open_centre()
        early = read(self.publication, self.old.number)
        later = read(self.publication, self.new.number)
        self.assertEqual((early.body['cases'][0]['contrast']['value'],
                          later.body['cases'][0]['contrast']['value']), ('3', '6'))
        self.assertEqual(early.parents, (self.a_in.key, self.b_in.key))
        self.assertEqual(later.parents, (self.a_in.key, self.b_next_in.key))
        self.assertEqual(early, self.old)
        self.assertEqual(later, self.new)
        self.assertNotEqual(early.receipt, later.receipt)
        with self.assertRaises(KeyError):
            read(self.publication, self.new.number + 1)

    def test_archive_copy_uses_actual_signed_material(self):
        self.record_correction()
        self.centre.close()
        self.open_centre()
        destination = self.root / 'archived.json'
        export_report(self.publication, self.old.number, destination)
        exported = json.loads(destination.read_text(encoding='utf-8'))
        self.assertEqual(exported, {
            'number': self.old.number, 'body': self.old.body, 'parents': list(self.old.parents),
            'parent_checksums': list(self.old.parent_checksums), 'receipt': self.old.receipt.document(),
        })
        self.assertEqual(exported['body']['cases'][0]['contrast']['value'], '3')

    def test_reopen_init_preserves_all_business_state(self):
        self.record_correction()
        self.centre.close()
        self.open_centre()
        self.open_sources()
        self.catalog.initialize()
        for store in self.revisions.values():
            store.initialize()
        self.intake.initialize()
        self.publication.initialize()
        self.assertEqual(self.catalog.get('R'), self.roster)
        self.assertEqual(self.revisions['A'].get(self.a.revision_id), self.a)
        self.assertEqual(self.revisions['B'].get(self.b.revision_id), self.b)
        self.assertEqual(self.revisions['B'].get(self.b_next.revision_id), self.b_next)
        self.close_sources()
        for entry in (self.a_in, self.b_in, self.b_next_in):
            self.assertEqual(self.intake.get(entry.key), entry)
        self.assertEqual(read(self.publication, self.old.number), self.old)
        self.assertEqual(read(self.publication, self.new.number), self.new)
        self.assertEqual(self.publication_counts(), (2, 4, 2))
