from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path

from .models import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    fingerprint TEXT PRIMARY KEY,
    portal_ids TEXT NOT NULL,
    urls TEXT NOT NULL,
    last_rent INTEGER NOT NULL,
    last_total INTEGER,
    first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notified_at TEXT
);
CREATE TABLE IF NOT EXISTS saved_homes (
    fingerprint TEXT PRIMARY KEY,
    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hidden_buildings (
    normalized_street TEXT PRIMARY KEY,
    hidden_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def normalize_street(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else " " for character in value.lower())
    return " ".join(cleaned.split())


def fingerprint(listing: Listing) -> str:
    rounded_rent = 25 * round(listing.rent_pcm / 25)
    return f"{listing.outcode}|{rounded_rent}|{normalize_street(listing.street or listing.title)}"


def callback_token(value: str) -> str:
    return sha256(value.encode()).hexdigest()[:32]


class ListingStore:
    def __init__(self, path: str | Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def is_hidden(self, listing: Listing) -> bool:
        street = normalize_street(listing.street or listing.title)
        row = self.connection.execute(
            "SELECT 1 FROM hidden_buildings WHERE normalized_street = ?",
            (callback_token(street),),
        ).fetchone()
        return row is not None

    def record(self, listing: Listing) -> tuple[bool, bool]:
        key = fingerprint(listing)
        existing = self.connection.execute(
            """
            SELECT last_rent, last_total, portal_ids, urls, notified_at
            FROM listings
            WHERE fingerprint = ?
            """,
            (key,),
        ).fetchone()
        portal_ids = listing.merged_ids or {listing.portal.value: listing.portal_listing_id}
        urls = listing.merged_urls or {listing.portal.value: listing.url}
        price_drop = False
        if existing:
            portal_ids.update(json.loads(existing["portal_ids"]))
            urls.update(json.loads(existing["urls"]))
            price_drop = listing.rent_pcm < existing["last_rent"] or (
                listing.total_monthly_cost is not None
                and existing["last_total"] is not None
                and listing.total_monthly_cost < existing["last_total"]
            )
        listing.merged_urls = urls
        self.connection.execute(
            """
            INSERT INTO listings (fingerprint, portal_ids, urls, last_rent, last_total)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET
                portal_ids=excluded.portal_ids,
                urls=excluded.urls,
                last_rent=excluded.last_rent,
                last_total=excluded.last_total,
                last_seen=CURRENT_TIMESTAMP
            """,
            (
                key,
                json.dumps(portal_ids),
                json.dumps(urls),
                listing.rent_pcm,
                listing.total_monthly_cost,
            ),
        )
        self.connection.commit()
        needs_notification = existing is None or existing["notified_at"] is None
        return needs_notification, price_drop

    def mark_notified(self, listing: Listing) -> None:
        self.connection.execute(
            "UPDATE listings SET notified_at = CURRENT_TIMESTAMP WHERE fingerprint = ?",
            (fingerprint(listing),),
        )
        self.connection.commit()

    def save(self, token: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO saved_homes (fingerprint) VALUES (?)",
            (token,),
        )
        self.connection.commit()

    def hide(self, street_token: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO hidden_buildings (normalized_street) VALUES (?)",
            (street_token,),
        )
        self.connection.commit()
