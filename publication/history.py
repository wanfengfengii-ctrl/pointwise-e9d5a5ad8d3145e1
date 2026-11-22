from publication.store import PublicationStore, SignedReport


def read(store: PublicationStore, number: int) -> SignedReport:
    return store.get_by_number(number)
