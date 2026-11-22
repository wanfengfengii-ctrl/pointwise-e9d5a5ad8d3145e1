from observations.revisions import RevisionStore, StationRevision, validate_station
from observations.validation import validate_observation_rows
from registry.runs import RunCatalog


def revise(catalog: RunCatalog, revisions: RevisionStore, station: str, run_id: str,
           rows, previous: int | None = None) -> StationRevision:
    validate_station(station)
    roster = catalog.get(run_id)
    equations = validate_observation_rows(roster, rows)
    return revisions.freeze(station, run_id, equations, rows, previous)
