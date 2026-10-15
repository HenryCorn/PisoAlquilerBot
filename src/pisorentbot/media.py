from __future__ import annotations

import asyncio
import io
import os
from collections.abc import Iterable
from urllib.parse import urlencode

import httpx
import pytesseract
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .models import Listing

WIDTH, HEIGHT = 1200, 500
MAP_WIDTH = 480
OXFORD_CIRCUS = (51.5152, -0.1419)
SHOREDITCH = (51.5245, -0.0789)


def _map_url(listing: Listing) -> str | None:
    api_key = os.getenv("GEOAPIFY_API_KEY")
    if not api_key or listing.latitude is None or listing.longitude is None:
        return None
    points = [
        (listing.latitude, listing.longitude),
        OXFORD_CIRCUS,
        SHOREDITCH,
    ]
    min_lat, max_lat = min(point[0] for point in points), max(point[0] for point in points)
    min_lon, max_lon = min(point[1] for point in points), max(point[1] for point in points)
    params = {
        "style": "osm-bright",
        "width": MAP_WIDTH,
        "height": HEIGHT,
        "area": f"rect:{min_lon - .01},{min_lat - .01},{max_lon + .01},{max_lat + .01}",
        "marker": "|".join(
            [
                f"lonlat:{listing.longitude},{listing.latitude};color:%23e53935;size:large",
                f"lonlat:{OXFORD_CIRCUS[1]},{OXFORD_CIRCUS[0]};color:%231e88e5;text:A",
                f"lonlat:{SHOREDITCH[1]},{SHOREDITCH[0]};color:%238e24aa;text:B",
            ]
        ),
        "geometry": "|".join(
            [
                "polyline:"
                f"{listing.longitude},{listing.latitude},{OXFORD_CIRCUS[1]},{OXFORD_CIRCUS[0]}"
                ";color:%231e88e5;opacity:60;width:3",
                "polyline:"
                f"{listing.longitude},{listing.latitude},{SHOREDITCH[1]},{SHOREDITCH[0]}"
                ";color:%238e24aa;opacity:60;width:3",
            ]
        ),
        "apiKey": api_key,
    }
    return f"https://maps.geoapify.com/v1/staticmap?{urlencode(params, safe=':,;|%')}"


async def _download(client: httpx.AsyncClient, url: str | None) -> Image.Image | None:
    if not url:
        return None
    try:
        response = await client.get(url)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except (httpx.HTTPError, OSError):
        return None


def _cover(image: Image.Image | None, size: tuple[int, int], label: str) -> Image.Image:
    if image:
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    placeholder = Image.new("RGB", size, "#20242b")
    draw = ImageDraw.Draw(placeholder)
    font = ImageFont.load_default(size=22)
    draw.text((size[0] // 2, size[1] // 2), label, fill="white", font=font, anchor="mm")
    return placeholder


def select_images(listing: Listing) -> tuple[str | None, list[str]]:
    floorplan = next(
        (
            url
            for url in listing.image_urls
            if any(word in url.lower() for word in ("floorplan", "floor-plan", "layout", "plan"))
        ),
        None,
    )
    interiors = [url for url in listing.image_urls if url != floorplan]
    return floorplan, interiors[:2]


async def floorplan_text(client: httpx.AsyncClient, listing: Listing) -> str:
    floorplan, _ = select_images(listing)
    image = await _download(client, floorplan)
    if not image:
        return ""
    try:
        return await asyncio.to_thread(pytesseract.image_to_string, image)
    except (OSError, RuntimeError, pytesseract.TesseractNotFoundError):
        return ""


async def build_banner(client: httpx.AsyncClient, listing: Listing) -> io.BytesIO:
    floorplan_url, interior_urls = select_images(listing)
    urls: Iterable[str | None]
    if floorplan_url:
        urls = [floorplan_url, interior_urls[0] if interior_urls else None]
    else:
        urls = [*interior_urls, None][:2]
    map_image, *property_images = await asyncio.gather(
        _download(client, _map_url(listing)),
        *(_download(client, url) for url in urls),
    )
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "white")
    canvas.paste(_cover(map_image, (MAP_WIDTH, HEIGHT), "Map unavailable"), (0, 0))
    panel_width = (WIDTH - MAP_WIDTH) // 2
    for index in range(2):
        image = property_images[index] if index < len(property_images) else None
        canvas.paste(
            _cover(image, (panel_width, HEIGHT), "Photo unavailable"),
            (MAP_WIDTH + index * panel_width, 0),
        )
    output = io.BytesIO()
    canvas.save(output, "JPEG", quality=88, optimize=True)
    output.seek(0)
    output.name = f"{listing.portal_listing_id}.jpg"
    return output
