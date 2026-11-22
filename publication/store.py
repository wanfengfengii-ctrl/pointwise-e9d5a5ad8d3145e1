import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from publication.receipts import Receipt, canonical_json, make_receipt


@dataclass(frozen=True, slots=True)
class SignedReport:
    number: int
    body: dict
    parents: tuple[str, str]
    parent_checksums: tuple[str, str]
    receipt: Receipt


class PublicationStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        if self.db.in_transaction:
            raise ValueError('publication initialization requires no pending transaction')
        self.db.execute('PRAGMA foreign_keys = ON')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                number INTEGER PRIMARY KEY,
                body TEXT NOT NULL
            )
        ''')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS report_parents (
                number INTEGER NOT NULL REFERENCES reports(number),
                position INTEGER NOT NULL CHECK (position IN (0, 1)),
                piece_id TEXT NOT NULL,
                checksum TEXT NOT NULL,
                PRIMARY KEY (number, position)
            )
        ''')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                number INTEGER PRIMARY KEY REFERENCES reports(number),
                document TEXT NOT NULL
            )
        ''')

    def commit_report(self, body: dict, parents: tuple[str, str], checksums: tuple[str, str],
                      *, after_body: Callable[[], None] | None = None) -> SignedReport:
        if after_body is not None and not callable(after_body):
            raise ValueError('after_body must be callable')
        if len(parents) != 2 or len(checksums) != 2 or parents[0] == parents[1]:
            raise ValueError('a report requires two distinct fixed parents')
        encoded_body = canonical_json(body)
        snapshot = json.loads(encoded_body)
        if snapshot.get('parents') != list(parents) or snapshot.get('parent_checksums') != list(checksums):
            raise ValueError('report body does not match its parents')
        if self.db.in_transaction:
            raise ValueError('signing requires a connection without a pending transaction')

        self.db.execute('BEGIN IMMEDIATE')
        try:
            number = self.db.execute('INSERT INTO reports(body) VALUES (?)', (encoded_body,)).lastrowid
            self.db.executemany('''
                INSERT INTO report_parents(number, position, piece_id, checksum) VALUES (?, ?, ?, ?)
            ''', [(number, position, parent, checksum)
                  for position, (parent, checksum) in enumerate(zip(parents, checksums))])
            if after_body is not None:
                after_body()
            receipt = make_receipt(number, snapshot, parents, checksums)
            self.db.execute('INSERT INTO receipts(number, document) VALUES (?, ?)',
                            (number, canonical_json(receipt.document())))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        return SignedReport(number, snapshot, parents, checksums, receipt)

    def get_by_number(self, number: int) -> SignedReport:
        if type(number) is not int or not 1 <= number <= 2**63 - 1:
            raise ValueError('invalid report number')
        row = self.db.execute('''
            SELECT r.body, a.piece_id, a.checksum, b.piece_id, b.checksum, receipt.document
            FROM reports AS r
            JOIN report_parents AS a ON a.number = r.number AND a.position = 0
            JOIN report_parents AS b ON b.number = r.number AND b.position = 1
            JOIN receipts AS receipt ON receipt.number = r.number
            WHERE r.number = ?
        ''', (number,)).fetchone()
        if row is None:
            raise KeyError(number)
        encoded_body, a_id, a_checksum, b_id, b_checksum, encoded_receipt = row
        saved = json.loads(encoded_receipt)
        receipt = Receipt(saved['report_number'], tuple(saved['parent_ids']),
                          tuple(saved['parent_checksums']), saved['body_checksum'], saved['receipt_id'])
        return SignedReport(number, json.loads(encoded_body), (a_id, b_id), (a_checksum, b_checksum), receipt)
