from test_filtering import listing

from pisorentbot.store import ListingStore


def test_unnotified_listing_is_retried(tmp_path):
    store = ListingStore(tmp_path / "state.db")
    item = listing()
    item.total_monthly_cost = 1484
    try:
        assert store.record(item) == (True, False)
        assert store.record(item) == (True, False)
        store.mark_notified(item)
        assert store.record(item) == (False, False)
    finally:
        store.close()
