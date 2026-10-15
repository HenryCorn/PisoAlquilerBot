import json
import sqlite3
from pathlib import Path

import httpx
from test_filtering import listing

from pisorentbot.store import (
    SCHEMA,
    D1ListingStore,
    ListingStore,
    callback_token,
    normalize_street,
)


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


def d1_client() -> httpx.Client:
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token"
        body = json.loads(request.content)
        rows = [dict(row) for row in database.execute(body["sql"], body["params"])]
        database.commit()
        return httpx.Response(200, json={"success": True, "result": [{"results": rows}]})

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_d1_store_matches_sqlite_behaviour():
    store = D1ListingStore("account", "database", "token", client=d1_client())
    item = listing()
    item.total_monthly_cost = 1484
    try:
        assert store.record(item) == (True, False)
        store.mark_notified(item)
        assert store.record(item) == (False, False)
        item.total_monthly_cost -= 20
        assert store.record(item) == (False, True)
        assert not store.is_hidden(item)
        store.hide(callback_token(normalize_street(item.street or item.title)))
        assert store.is_hidden(item)
    finally:
        store.close()


def test_worker_schema_matches_python_schema():
    worker_schema = (Path(__file__).parents[1] / "worker" / "schema.sql").read_text()
    assert worker_schema.strip() == SCHEMA.strip()
