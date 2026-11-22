import hashlib
import json
from dataclasses import dataclass


def canonical_json(document) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class Receipt:
    report_number: int
    parent_ids: tuple[str, str]
    parent_checksums: tuple[str, str]
    body_checksum: str
    receipt_id: str

    def document(self) -> dict:
        return {
            'report_number': self.report_number,
            'parent_ids': list(self.parent_ids),
            'parent_checksums': list(self.parent_checksums),
            'body_checksum': self.body_checksum,
            'receipt_id': self.receipt_id,
        }


def make_receipt(number: int, body: dict, parents: tuple[str, str], checksums: tuple[str, str]) -> Receipt:
    body_checksum = _digest(canonical_json(body))
    receipt_id = _digest(canonical_json([number, parents, checksums, body_checksum]))
    return Receipt(number, parents, checksums, body_checksum, receipt_id)
