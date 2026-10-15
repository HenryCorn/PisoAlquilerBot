from __future__ import annotations

import os

import httpx

from .models import Commute, Listing

OXFORD_CIRCUS = (51.5152, -0.1419)
SHOREDITCH = (51.5245, -0.0789)


class TflJourneyPlanner:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def enrich(self, listing: Listing) -> None:
        if listing.latitude is None or listing.longitude is None:
            return
        origin = f"{listing.latitude},{listing.longitude}"
        listing.commute_a = await self._journey(origin, OXFORD_CIRCUS)
        listing.commute_b = await self._journey(origin, SHOREDITCH)

    async def _journey(self, origin: str, destination: tuple[float, float]) -> Commute | None:
        params = {
            "mode": "bus,overground,tube,dlr,elizabeth-line,national-rail",
            "journeyPreference": "leasttime",
        }
        if app_id := os.getenv("TFL_APP_ID"):
            params["app_id"] = app_id
        if app_key := os.getenv("TFL_APP_KEY"):
            params["app_key"] = app_key
        target = f"{destination[0]},{destination[1]}"
        response = await self.client.get(
            f"https://api.tfl.gov.uk/Journey/JourneyResults/{origin}/to/{target}",
            params=params,
        )
        response.raise_for_status()
        journeys = response.json().get("journeys", [])
        if not journeys:
            return None
        journey = min(journeys, key=lambda value: value.get("duration", 10_000))
        legs = journey.get("legs", [])
        summary = " → ".join(
            leg.get("instruction", {}).get("summary", "").strip()
            for leg in legs
            if leg.get("instruction", {}).get("summary")
        )
        return Commute(int(journey["duration"]), summary)
