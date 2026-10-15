from __future__ import annotations

import httpx

from .models import Listing


def crime_score(incident_count: int, incidents_for_max_score: int) -> int:
    return min(100, round(100 * incident_count / incidents_for_max_score))


async def enrich_crime(
    client: httpx.AsyncClient,
    listing: Listing,
    incidents_for_max_score: int,
) -> None:
    if listing.latitude is None or listing.longitude is None:
        return
    response = await client.get(
        "https://data.police.uk/api/crimes-street/all-crime",
        params={"lat": listing.latitude, "lng": listing.longitude},
    )
    response.raise_for_status()
    listing.crime_score = crime_score(len(response.json()), incidents_for_max_score)
