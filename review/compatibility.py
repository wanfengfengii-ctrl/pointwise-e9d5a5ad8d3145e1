from dataclasses import dataclass

from review.intake import IntakeStore, ReceivedDrift, ReceivedPiece


@dataclass(frozen=True, slots=True)
class MatchedParents:
    a: ReceivedPiece
    b: ReceivedPiece

    @property
    def ids(self) -> tuple[str, str]:
        return self.a.key, self.b.key

    @property
    def checksums(self) -> tuple[str, str]:
        return self.a.piece.checksum, self.b.piece.checksum

    @property
    def run_id(self) -> str:
        return self.a.piece.run_id

    @property
    def case_ids(self) -> tuple[str | None, ...]:
        return self.a.piece.case_ids


def match_parents(store: IntakeStore, a_key: str, b_key: str) -> MatchedParents:
    a = store.get(a_key)
    b = store.get(b_key)
    if (a.piece.station, b.piece.station) != ('A', 'B'):
        raise ValueError('the specified parents must be station A and station B, in that order')
    if a.piece.run_id != b.piece.run_id:
        raise ValueError('the specified parents belong to different runs')
    if a.piece.roster_digest != b.piece.roster_digest or a.piece.case_ids != b.piece.case_ids:
        raise ValueError('the specified parents use different roster scopes')
    return MatchedParents(a, b)


@dataclass(frozen=True, slots=True)
class MatchedDriftParents:
    a: ReceivedDrift
    b: ReceivedDrift

    @property
    def ids(self) -> tuple[str, str]:
        return self.a.key, self.b.key

    @property
    def checksums(self) -> tuple[str, str]:
        return self.a.piece.checksum, self.b.piece.checksum

    @property
    def run_id(self) -> str:
        return self.a.piece.run_id

    @property
    def work_box(self) -> tuple:
        return self.a.piece.work_box

    @property
    def case_ids(self) -> tuple[str | None, ...]:
        return self.a.piece.case_ids


def match_drift_parents(store: IntakeStore, a_key: str, b_key: str) -> MatchedDriftParents:
    a = store.get_drift(a_key)
    b = store.get_drift(b_key)
    if (a.piece.station, b.piece.station) != ('A', 'B'):
        raise ValueError('the specified parents must be station A and station B, in that order')
    if a.piece.run_id != b.piece.run_id:
        raise ValueError('the specified parents belong to different runs')
    if a.piece.roster_digest != b.piece.roster_digest or a.piece.case_ids != b.piece.case_ids:
        raise ValueError('the specified parents use different roster scopes')
    if a.piece.work_box != b.piece.work_box:
        raise ValueError('the specified parents use different work boxes')
    return MatchedDriftParents(a, b)
