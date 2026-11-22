import json
from pathlib import Path

from publication.history import read
from publication.store import PublicationStore


def export_report(store: PublicationStore, number: int, path: str | Path) -> Path:
    saved = read(store, number)
    document = {
        'number': saved.number,
        'body': saved.body,
        'parents': saved.parents,
        'parent_checksums': saved.parent_checksums,
        'receipt': saved.receipt.document(),
    }
    destination = Path(path)
    destination.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return destination
