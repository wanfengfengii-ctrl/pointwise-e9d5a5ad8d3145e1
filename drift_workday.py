from contextlib import ExitStack, closing
import json
from pathlib import Path
import sqlite3

from evidence.issue import issue
from observations.intake import revise
from observations.revisions import RevisionStore
from publication.history import read
from publication.sign import sign
from publication.store import PublicationStore
from registry.runs import RunCatalog
from review.intake import IntakeStore, receive
from review.joint import assess


def load_workday(name="crossed"):
    path = Path(__file__).resolve().parent / "samples" / "drift.json"
    return json.loads(path.read_text(encoding="utf-8"))[name]


def freeze_workday(stack, sample, connect):
    def open_store(filename, store_type):
        store = store_type(stack.enter_context(closing(connect(filename))))
        store.initialize()
        return store

    catalog = open_store("catalog.sqlite", RunCatalog)
    catalog.register(sample["run_id"], sample["batches"])
    stations = {station: open_store(f"station-{station}.sqlite", RevisionStore)
                for station in ("A", "B")}
    frozen = {}
    for label, entry in sample["versions"].items():
        station = entry["station"]
        previous = frozen[entry["previous"]].revision_id if "previous" in entry else None
        frozen[label] = revise(catalog, stations[station], station, sample["run_id"],
                               entry["rows"], previous)
    return catalog, stations, frozen


def interrupt_receipt():
    raise RuntimeError("sample receipt desk interrupted")


def baseline_comparison():
    sample = load_workday()
    with closing(sqlite3.connect(":memory:")) as centre:
        intake = IntakeStore(centre)
        archive = PublicationStore(centre)
        intake.initialize()
        archive.initialize()
        with ExitStack() as sources:
            catalog, stations, frozen = freeze_workday(
                sources, sample, lambda filename: sqlite3.connect(":memory:"))
            entries = {label: receive(intake, issue(catalog, stations[rev.station], rev.revision_id))
                       for label, rev in frozen.items()}
        left = entries["a"]
        for label in ("b", "b_corrected"):
            right = entries[label]
            if left.piece.cases != right.piece.cases:
                raise AssertionError("the V1 fixture must have identical public case relations")
            result = assess(intake, left.key, right.key, sample["contrast"], (0, 0))
            report = sign(archive, intake, result)
            observed = read(archive, report.number).body["cases"]
            expected = [{"excluded_batch": None, "contrast": {"kind": "all_rationals"},
                         "supports_claim": True}]
            if observed != expected:
                raise AssertionError(f"unexpected V1 report for {label}: {observed!r}")
            print(f"{label}: {json.dumps(observed, ensure_ascii=False)}")


if __name__ == "__main__":
    baseline_comparison()
