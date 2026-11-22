from pathlib import Path

from evidence.envelope import PieceEnvelope, decode_envelope, encode_envelope


def export_piece(piece: PieceEnvelope, path: str | Path) -> Path:
    destination = Path(path)
    destination.write_text(encode_envelope(piece) + '\n', encoding='utf-8')
    return destination


def load_piece(path: str | Path) -> PieceEnvelope:
    return decode_envelope(Path(path).read_text(encoding='utf-8'))
