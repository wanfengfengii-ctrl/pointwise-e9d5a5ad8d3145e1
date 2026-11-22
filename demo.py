import json
import sqlite3
from contextlib import ExitStack, closing
from pathlib import Path
from tempfile import TemporaryDirectory

from evidence.handoff import export_piece, load_piece
from evidence.issue import issue
from observations.intake import revise
from observations.revisions import RevisionStore
from publication.export import export_report
from publication.history import read
from publication.sign import sign
from publication.store import PublicationStore
from registry.runs import RunCatalog
from review.intake import IntakeStore, receive
from review.joint import assess


def _open(stack, root, filename, store_type):
    store = store_type(stack.enter_context(closing(sqlite3.connect(root / filename))))
    store.initialize()
    return store


def _ship(root, catalog, store, revision_id):
    piece = issue(catalog, store, revision_id)
    return export_piece(piece, root / f'{piece.piece_id}.json')


def _first_shift(root, sample):
    with ExitStack() as stack:
        catalog = _open(stack, root, 'catalog.db', RunCatalog)
        a_store = _open(stack, root, 'station-A.db', RevisionStore)
        b_store = _open(stack, root, 'station-B.db', RevisionStore)
        run_id = sample['run_id']
        catalog.register(run_id, sample['batches'])
        a = revise(catalog, a_store, 'A', run_id, sample['A'])
        b = revise(catalog, b_store, 'B', run_id, sample['B'])
        return _ship(root, catalog, a_store, a.revision_id), _ship(root, catalog, b_store, b.revision_id), b.revision_id


def _correction(root, sample, previous):
    with ExitStack() as stack:
        catalog = _open(stack, root, 'catalog.db', RunCatalog)
        store = _open(stack, root, 'station-B.db', RevisionStore)
        updated = revise(catalog, store, 'B', sample['run_id'], sample['corrected_B'], previous)
        return _ship(root, catalog, store, updated.revision_id)


def _sign(root, sample, a_path, b_path, claim):
    with closing(sqlite3.connect(root / 'centre.db')) as db:
        inbox = IntakeStore(db)
        reports = PublicationStore(db)
        inbox.initialize()
        reports.initialize()
        a, b = (receive(inbox, load_piece(path)) for path in (a_path, b_path))
        return sign(reports, inbox, assess(inbox, a.key, b.key, sample['contrast'], claim))


def main():
    sample_path = Path(__file__).with_name('samples') / 'workday.json'
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    with TemporaryDirectory() as directory:
        root = Path(directory)
        a_path, b_path, previous = _first_shift(root, sample)
        earlier = _sign(root, sample, a_path, b_path, sample['claim'])
        corrected_path = _correction(root, sample, previous)
        later = _sign(root, sample, a_path, corrected_path, sample['corrected_claim'])
        with closing(sqlite3.connect(root / 'centre.db')) as db:
            reports = PublicationStore(db)
            reports.initialize()
            original = read(reports, earlier.number)
            corrected = read(reports, later.number)
            destination = export_report(reports, earlier.number, root / 'original-report.json')
            archive = json.loads(destination.read_text(encoding='utf-8'))

        expected = {'original': '3', 'corrected': '6', 'both_claims_supported': True}
        actual = {'original': original.body['cases'][0]['contrast']['value'],
                  'corrected': corrected.body['cases'][0]['contrast']['value'],
                  'both_claims_supported': original.body['supported'] and corrected.body['supported']}
        expected_archive = {'original': '3', 'kept_parents': True, 'kept_receipt': True}
        actual_archive = {'original': archive['body']['cases'][0]['contrast']['value'],
                          'kept_parents': archive['parents'] == list(earlier.parents),
                          'kept_receipt': archive['receipt'] == earlier.receipt.document()}
        if actual != expected or actual_archive != expected_archive or original != earlier or corrected != later:
            raise RuntimeError('the reopened results do not match the workday calculation and history')
        if original.parents[0] != corrected.parents[0] or original.parents[1] == corrected.parents[1]:
            raise RuntimeError('the correction did not select exactly the new station B piece')
        print(json.dumps({
            'run': sample['run_id'],
            'original': {'number': original.number, 'contrast_um': actual['original'],
                         'parents': original.parents, 'receipt': original.receipt.receipt_id},
            'corrected': {'number': corrected.number, 'contrast_um': actual['corrected'],
                          'parents': corrected.parents, 'receipt': corrected.receipt.receipt_id},
        }, ensure_ascii=False, indent=2))
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'T8.read_original', 'input': sample,
            'expected': expected, 'actual': actual,
            'downstream_expected': expected_archive, 'downstream_actual': actual_archive,
            'code_paths': ['observations/revisions.py', 'evidence/issue.py', 'review/joint.py',
                           'publication/history.py', 'publication/export.py'],
            'oracle': 'A gives x=5-4=1. The two B worksheets give y=2 and y=5 after conversion from mm.'
        }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
