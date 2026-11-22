import sqlite3
from dataclasses import dataclass

from evidence.drift import DriftPiece, decode_drift_piece, encode_drift_piece
from evidence.envelope import PieceEnvelope, decode_envelope, encode_envelope, validate_digest


@dataclass(frozen=True, slots=True)
class ReceivedPiece:
    key: str
    piece: PieceEnvelope


@dataclass(frozen=True, slots=True)
class ReceivedDrift:
    key: str
    piece: DriftPiece


class IntakeStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS received_pieces (
                piece_id TEXT PRIMARY KEY,
                envelope TEXT NOT NULL
            )
        ''')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS received_drift_pieces (
                piece_key TEXT PRIMARY KEY,
                document TEXT NOT NULL
            )
        ''')

    def _encoded(self, key: str) -> str:
        row = self.db.execute('SELECT envelope FROM received_pieces WHERE piece_id = ?', (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return row[0]

    def _drift_document(self, key: str):
        row = self.db.execute(
            'SELECT document FROM received_drift_pieces WHERE piece_key = ?', (key,)).fetchone()
        return None if row is None else row[0]

    def _accept(self, piece: PieceEnvelope) -> ReceivedPiece:
        encoded = encode_envelope(piece)
        if self.db.in_transaction:
            raise ValueError('receiving requires a connection without a pending transaction')
        with self.db:
            self.db.execute('''
                INSERT INTO received_pieces (piece_id, envelope) VALUES (?, ?)
                ON CONFLICT(piece_id) DO NOTHING
            ''', (piece.piece_id, encoded))
            if self._encoded(piece.piece_id) != encoded:
                raise ValueError(f'conflicting station piece: {piece.piece_id}')
        return ReceivedPiece(piece.piece_id, piece)

    def _accept_drift(self, piece: DriftPiece) -> ReceivedDrift:
        encoded = encode_drift_piece(piece)
        if self.db.in_transaction:
            raise ValueError('receiving requires a connection without a pending transaction')
        with self.db:
            self.db.execute('''
                INSERT INTO received_drift_pieces (piece_key, document) VALUES (?, ?)
                ON CONFLICT(piece_key) DO NOTHING
            ''', (piece.checksum, encoded))
            if self._drift_document(piece.checksum) != encoded:
                raise ValueError(f'conflicting drift piece: {piece.checksum}')
        return ReceivedDrift(piece.checksum, piece)

    def get(self, key: str) -> ReceivedPiece:
        validate_digest(key, 'intake key')
        try:
            encoded = self._encoded(key)
        except KeyError:
            if self._drift_document(key) is not None:
                raise ValueError('a drift piece cannot be used for V1 review') from None
            raise
        piece = decode_envelope(encoded)
        if piece.piece_id != key:
            raise ValueError('stored piece does not match its intake key')
        return ReceivedPiece(key, piece)

    def get_drift(self, key: str) -> ReceivedDrift:
        validate_digest(key, 'intake key')
        document = self._drift_document(key)
        if document is None:
            try:
                self._encoded(key)
            except KeyError:
                raise KeyError(key) from None
            raise ValueError('a V1 station piece cannot be used for drift review')
        piece = decode_drift_piece(document)
        if piece.checksum != key:
            raise ValueError('stored drift piece does not match its intake key')
        return ReceivedDrift(key, piece)


def receive(store: IntakeStore, piece: PieceEnvelope | str) -> ReceivedPiece:
    encoded = encode_envelope(piece) if isinstance(piece, PieceEnvelope) else piece
    return store._accept(decode_envelope(encoded))


def receive_drift(store: IntakeStore, encoded: str) -> ReceivedDrift:
    return store._accept_drift(decode_drift_piece(encoded))
