import json
import sqlite3
from contextlib import ExitStack, closing
from pathlib import Path
from tempfile import TemporaryDirectory

from drift_workday import freeze_workday, load_workday
from evidence.handoff import export_piece, load_piece
from evidence.issue import issue, issue_drift
from observations.intake import revise
from observations.revisions import RevisionStore
from publication.export import export_report
from publication.history import read
from publication.sign import sign, sign_drift
from publication.store import PublicationStore
from registry.runs import RunCatalog
from review.intake import IntakeStore, receive, receive_drift
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


def _drift_demo(root):
    sample = load_workday('crossed')
    centre_path = root / 'drift-centre.db'
    with closing(sqlite3.connect(centre_path)) as centre:
        intake = IntakeStore(centre)
        reports = PublicationStore(centre)
        intake.initialize()
        reports.initialize()
        with ExitStack() as sources:
            catalog, stations, frozen = freeze_workday(
                sources, sample, lambda filename: sqlite3.connect(root / filename))
            received = {}
            for label, revision in frozen.items():
                entry = sample['versions'][label]
                received[label] = receive_drift(intake, issue_drift(
                    catalog, stations[revision.station], revision.revision_id,
                    sample['work_box'], entry['certified_bounds']))
        # The three source connections are closed; signing works offline.
        signed = {}
        for right in ('b', 'b_corrected'):
            for window in ('full', 'early', 'point'):
                signed[right, window] = sign_drift(
                    reports, intake, received['a'].key, received[right].key,
                    sample['windows'][window], sample['contrast'])
    with closing(sqlite3.connect(centre_path)) as reopened:
        archive = PublicationStore(reopened)
        archive.initialize()
        restored = {key: read(archive, report.number) for key, report in signed.items()}
        destination = export_report(archive, signed['b', 'full'].number,
                                    root / 'drift-report.json')
        exported = json.loads(destination.read_text(encoding='utf-8'))
    expected_cases = {
        ('b', 'full'): [{'excluded_batch': None, 'range': ['1', '1']}],
        ('b', 'early'): [],
        ('b', 'point'): [{'excluded_batch': None, 'range': ['1', '1']}],
        ('b_corrected', 'full'): [{'excluded_batch': None, 'range': ['0', '2']}],
        ('b_corrected', 'early'): [{'excluded_batch': None, 'range': ['3/2', '2']}],
        ('b_corrected', 'point'): [{'excluded_batch': None, 'range': ['1', '1']}],
    }
    actual_cases = {key: report.body['cases'] for key, report in signed.items()}
    if actual_cases != expected_cases or restored != signed:
        raise RuntimeError('the drift reports do not match the expected window table')
    if (exported['body'] != signed['b', 'full'].body
            or exported['parents'] != list(signed['b', 'full'].parents)
            or exported['receipt'] != signed['b', 'full'].receipt.document()):
        raise RuntimeError('the exported drift report does not match the signed original')
    print(json.dumps({
        'drift_run': sample['run_id'],
        'reports': {f'a+{right}@{window}': {'number': signed[right, window].number,
                                            'cases': cases}
                    for (right, window), cases in actual_cases.items()},
        'reopened_reads_match': True,
    }, ensure_ascii=False, indent=2))
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'drift.narrow_window',
        'input': {'parents': ['a+b', 'a+b_corrected'], 'windows': sample['windows'],
                  'contrast': sample['contrast']},
        'expected': {f'a+{right}@{window}': cases
                     for (right, window), cases in expected_cases.items()},
        'actual': {f'a+{right}@{window}': cases
                   for (right, window), cases in actual_cases.items()},
        'downstream_expected': 'signed reports are read back unchanged after the centre reopens',
        'downstream_actual': 'signed reports are read back unchanged after the centre reopens',
        'code_paths': ['evidence/issue.py', 'evidence/drift.py', 'evidence/polyhedra.py',
                       'review/intake.py', 'publication/sign.py', 'publication/history.py',
                       'publication/export.py'],
        'oracle': 'a and b meet only at (x,z)=(1,1); the early window [0,1/2] excludes it, '
                  'so the narrow report is empty while the full report fixes x at 1.'
    }, ensure_ascii=False, sort_keys=True))


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
        _drift_demo(root)


if __name__ == '__main__':
    main()
