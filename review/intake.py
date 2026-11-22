import sqlite3
from dataclasses import dataclass

from evidence.envelope import PieceEnvelope, decode_envelope, encode_envelope, validate_digest


@dataclass(frozen=True, slots=True)
class ReceivedPiece:
    key: str
    piece: PieceEnvelope


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

    def _encoded(self, key: str) -> str:
        row = self.db.execute('SELECT envelope FROM received_pieces WHERE piece_id = ?', (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return row[0]

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

    def get(self, key: str) -> ReceivedPiece:
        validate_digest(key, 'intake key')
        piece = decode_envelope(self._encoded(key))
        if piece.piece_id != key:
            raise ValueError('stored piece does not match its intake key')
        return ReceivedPiece(key, piece)


def receive(store: IntakeStore, piece: PieceEnvelope | str) -> ReceivedPiece:
    encoded = encode_envelope(piece) if isinstance(piece, PieceEnvelope) else piece
    return store._accept(decode_envelope(encoded))
