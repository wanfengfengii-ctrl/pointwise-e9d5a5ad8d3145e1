from evidence.envelope import PieceEnvelope, seal_envelope
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
