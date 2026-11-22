from evidence.drift import (encode_drift_piece, parse_certified_bounds, parse_work_box,
                            seal_drift_piece)
from evidence.envelope import PieceEnvelope, seal_envelope
from evidence.polyhedra import project_public_relation
from evidence.projection import project_public
from observations.revisions import RevisionStore
from registry.eligibility import eligible_batch_ids
from registry.runs import RunCatalog


def issue(catalog: RunCatalog, revisions: RevisionStore, revision_id: int) -> PieceEnvelope:
    revision = revisions.get(revision_id)
    roster = catalog.get(revision.run_id)
    cases = []
    for excluded in (None, *eligible_batch_ids(roster)):
        effective_rows = (row for row in revision.rows if row.batch_id != excluded)
        cases.append((excluded, project_public(effective_rows)))
    return seal_envelope(revision.run_id, revision.station, revision.revision_id, roster.digest, cases)


def issue_drift(catalog: RunCatalog, revisions: RevisionStore, revision_id: int,
                work_box, certified_bounds) -> str:
    """Issue a transmissible drift JSON text for a frozen revision."""
    box = parse_work_box(work_box)
    bounds = parse_certified_bounds(certified_bounds)
    revision = revisions.get(revision_id)
    roster = catalog.get(revision.run_id)
    cases = []
    for excluded in (None, *eligible_batch_ids(roster)):
        effective_rows = tuple(row for row in revision.rows if row.batch_id != excluded)
        cases.append((excluded, project_public_relation(effective_rows, box, bounds)))
    piece = seal_drift_piece(revision.run_id, revision.station, revision.revision_id,
                             roster.digest, box, cases)
    return encode_drift_piece(piece)
