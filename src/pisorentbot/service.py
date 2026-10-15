from __future__ import annotations

import asyncio
import logging
import os

import httpx

from .commute import TflJourneyPlanner
from .config import Settings
from .filtering import evaluate
from .media import floorplan_text
from .models import Listing, Portal
from .portals import OpenRentAdapter, PortalAdapter, RightmoveAdapter, ZooplaAdapter
from .store import ListingStore, fingerprint
from .telegram import TelegramNotifier

LOGGER = logging.getLogger(__name__)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "DNT": "1",
}


async def _collect(adapter: PortalAdapter) -> list[Listing]:
    try:
        return [listing async for listing in adapter.listings()]
    except (httpx.HTTPError, OSError, RuntimeError):
        LOGGER.exception("%s search failed", adapter.portal)
        return []


async def scrape(settings: Settings) -> tuple[list[Listing], list[Listing]]:
    timeout = settings.runtime["request_timeout_seconds"]
    async with httpx.AsyncClient(
        timeout=timeout,
        headers=HEADERS,
        follow_redirects=True,
    ) as client:
        browser_fallback = settings.runtime["browser_fallback"]
        adapters = [
            OpenRentAdapter(client, settings.portals["openrent_urls"], browser_fallback),
            RightmoveAdapter(client, settings.portals["rightmove_urls"], browser_fallback),
            ZooplaAdapter(client, settings.portals["zoopla_urls"], browser_fallback),
        ]
        batches = await asyncio.gather(*(_collect(adapter) for adapter in adapters))
        candidates = [listing for batch in batches for listing in batch]
        planner = TflJourneyPlanner(client)
        accepted: list[Listing] = []
        over_budget: list[Listing] = []
        for listing in candidates:
            listing.borough = settings.search["borough_by_outcode"].get(listing.outcode, "")
            ocr_text = await floorplan_text(client, listing)
            if ocr_text:
                listing.key_features.append(ocr_text)
            static_decision = evaluate(listing, settings, require_commute=False)
            if not static_decision.accepted:
                if static_decision.reason == "estimated total cost too high":
                    over_budget.append(listing)
                continue
            await planner.enrich(listing)
            if evaluate(listing, settings).accepted:
                accepted.append(listing)
        return accepted, over_budget


def merge_listings(listings: list[Listing]) -> list[Listing]:
    groups: dict[str, list[Listing]] = {}
    for listing in listings:
        groups.setdefault(fingerprint(listing), []).append(listing)
    merged: list[Listing] = []
    for group in groups.values():
        primary = next(
            (listing for listing in group if listing.portal is Portal.OPENRENT),
            group[0],
        )
        primary.merged_urls = {listing.portal.value: listing.url for listing in group}
        primary.merged_ids = {
            listing.portal.value: listing.portal_listing_id for listing in group
        }
        merged.append(primary)
    return sorted(merged, key=lambda item: (not item.priority, item.total_monthly_cost or 0))


async def run_once(settings: Settings) -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    store = ListingStore(settings.runtime["database_path"])
    notifier = TelegramNotifier(token, chat_id, store)
    try:
        scraped, over_budget = await scrape(settings)
        for listing in merge_listings(over_budget):
            store.record(listing)
        listings = merge_listings(scraped)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            sent = 0
            for listing in listings:
                if store.is_hidden(listing):
                    continue
                is_new, price_drop = store.record(listing)
                if not is_new and not price_drop:
                    continue
                sent += 1
                await notifier.send(client, listing, sent, price_drop)
                store.mark_notified(listing)
        LOGGER.info("Check complete: %d matching, %d sent", len(listings), sent)
        return sent
    finally:
        store.close()


async def daemon(settings: Settings) -> None:
    while True:
        try:
            await run_once(settings)
        except (httpx.HTTPError, RuntimeError):
            LOGGER.exception("Rental check failed")
        await asyncio.sleep(settings.runtime["poll_interval_seconds"])
