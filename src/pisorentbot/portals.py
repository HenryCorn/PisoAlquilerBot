from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable
from contextlib import suppress
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .models import Listing, Portal

LOGGER = logging.getLogger(__name__)
MONEY = re.compile(r"£\s*([\d,]+)")
BEDROOMS = re.compile(r"\b(\d+)\s*(?:bed|bedroom)", re.I)
POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*\d[A-Z]{2}\b", re.I)
FLOOR = re.compile(
    r"\b((?:first|second|third|fourth|fifth|top|upper|\d+(?:st|nd|rd|th)) floor)\b",
    re.I,
)
EPC = re.compile(r"\bEPC(?: rating)?\s*[:\-]?\s*([A-G])\b", re.I)
COUNCIL_BAND = re.compile(r"\bcouncil tax band\s*[:\-]?\s*([A-H])\b", re.I)
FURNISHING = re.compile(r"\b(part[- ]furnished|unfurnished|furnished)\b", re.I)
AVAILABLE = re.compile(
    r"\b(?:available|availability)\s*(?:from|:)?\s*(\d{1,2}\s+\w+\s+\d{4})\b",
    re.I,
)


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first(data: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        value = data.get(name)
        if value not in (None, "", [], {}):
            return value
    return default


def _number(value: Any, pattern: re.Pattern[str] = MONEY) -> int:
    if isinstance(value, int | float):
        return int(value)
    match = pattern.search(str(value))
    return int(match.group(1).replace(",", "")) if match else 0


def _available(text: str) -> date | None:
    match = AVAILABLE.search(text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d %B %Y").date()
    except ValueError:
        return None


def _json_scripts(soup: BeautifulSoup, portal: Portal) -> list[Any]:
    values: list[Any] = []
    script_ids = ["__NEXT_DATA__"] if portal in {Portal.ZOOPLA, Portal.OPENRENT} else []
    for script in soup.find_all("script"):
        content = script.string or script.get_text()
        if not content:
            continue
        if script.get("type") == "application/ld+json" or script.get("id") in script_ids:
            try:
                values.append(json.loads(content))
            except json.JSONDecodeError:
                continue
        if portal == Portal.RIGHTMOVE and "window.jsonModel" in content:
            match = re.search(r"window\.jsonModel\s*=\s*", content)
            if match:
                with suppress(json.JSONDecodeError):
                    value, _ = json.JSONDecoder().raw_decode(content[match.end() :])
                    values.append(value)
    return values


class PortalAdapter(ABC):
    portal: Portal

    def __init__(
        self,
        client: httpx.AsyncClient,
        search_urls: list[str],
        browser_fallback: bool = True,
    ) -> None:
        self.client = client
        self.search_urls = search_urls
        self.browser_fallback = browser_fallback

    async def listings(self) -> AsyncIterator[Listing]:
        seen_urls: set[str] = set()
        for search_url in self.search_urls:
            html = await self._fetch(search_url)
            urls = list(dict.fromkeys(self.detail_urls(html, search_url)))
            if urls:
                LOGGER.info("%s: %d listings on %s", self.portal, len(urls), search_url)
            else:
                title = BeautifulSoup(html, "lxml").title
                LOGGER.warning(
                    "%s: no listings on %s (page title %r, %d bytes; blocked?)",
                    self.portal,
                    search_url,
                    title.get_text(strip=True) if title else "",
                    len(html),
                )
            for url in urls:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                try:
                    yield self.parse(await self._fetch(url), url)
                except (ValueError, httpx.HTTPError) as error:
                    LOGGER.warning("%s listing failed: %s (%s)", self.portal, url, error)

    async def _fetch(self, url: str) -> str:
        response = await self.client.get(url)
        if response.status_code < 400 and len(response.text) > 2_000:
            return response.text
        if not self.browser_fallback:
            response.raise_for_status()
            return response.text
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(extra_http_headers=dict(self.client.headers))
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            html = await page.content()
            await browser.close()
            return html

    def detail_urls(self, html: str, base_url: str) -> Iterable[str]:
        soup = BeautifulSoup(html, "lxml")
        for anchor in soup.select("a[href]"):
            href_value = anchor.get("href", "")
            if not isinstance(href_value, str):
                continue
            href = href_value
            if self.is_detail_url(href):
                yield urljoin(base_url, href.split("?")[0])

    @abstractmethod
    def is_detail_url(self, href: str) -> bool: ...

    def parse(self, html: str, url: str) -> Listing:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)
        candidates = [
            node
            for state in _json_scripts(soup, self.portal)
            for node in _walk(state)
            if any(key in node for key in ("price", "rent", "bedrooms", "address"))
        ]
        data = max(candidates, key=lambda item: len(item), default={})
        page_title = soup.title.string if soup.title else ""
        title = str(_first(data, "name", "title", "displayAddress", default=page_title))
        description = str(_first(data, "description", "summary", default=text))
        searchable_text = f"{text} {title} {description}"
        address = _first(data, "address", "displayAddress", default=title)
        if isinstance(address, dict):
            address = " ".join(str(value) for value in address.values())
        price = _number(_first(data, "price", "rent", "priceValue", default=text))
        bedrooms = _number(_first(data, "bedrooms", "numberOfBedrooms", default=text), BEDROOMS)
        url_identifier = url.rstrip("/").split("/")[-1]
        identifier = str(_first(data, "id", "propertyId", "listingId", default=url_identifier))
        location = _first(data, "location", "geo", default={})
        images = _first(data, "images", "photos", "image", default=[])
        if isinstance(images, str):
            images = [images]
        elif isinstance(images, dict):
            images = list(images.values())
        image_urls = [
            str(_first(image, "url", "src", "original", default=""))
            if isinstance(image, dict)
            else str(image)
            for image in images
        ]
        postcode_match = POSTCODE.search(f"{address} {searchable_text}")
        floor_match = FLOOR.search(searchable_text)
        epc_match = EPC.search(searchable_text)
        band_match = COUNCIL_BAND.search(searchable_text)
        furnishing_match = FURNISHING.search(searchable_text)
        furnishing = _first(data, "furnishing", "furnishedType", default="")
        if not furnishing and furnishing_match:
            furnishing = furnishing_match.group(1).title()
        return Listing(
            portal=self.portal,
            portal_listing_id=identifier,
            url=url,
            title=title.strip(),
            description=description.strip(),
            rent_pcm=price,
            bedrooms=bedrooms,
            property_type=str(_first(data, "propertyType", "category", "@type")),
            postcode=postcode_match.group(0).upper() if postcode_match else "",
            street=str(address),
            furnishing=str(furnishing or "Unknown"),
            floor=floor_match.group(1).title() if floor_match else "Unknown",
            epc_rating=epc_match.group(1).upper() if epc_match else "",
            council_tax_band=band_match.group(1).upper() if band_match else "",
            available_from=_available(text),
            availability_text=(
                "Available immediately" if "available immediately" in text.lower() else ""
            ),
            latitude=float(_first(location, "latitude", "lat", default=0)) or None,
            longitude=float(_first(location, "longitude", "lng", "lon", default=0)) or None,
            image_urls=[value for value in image_urls if value.startswith("http")],
        )


class OpenRentAdapter(PortalAdapter):
    portal = Portal.OPENRENT

    def is_detail_url(self, href: str) -> bool:
        return "/property-to-rent/" in href


class RightmoveAdapter(PortalAdapter):
    portal = Portal.RIGHTMOVE

    def is_detail_url(self, href: str) -> bool:
        return "/properties/" in href


class ZooplaAdapter(PortalAdapter):
    portal = Portal.ZOOPLA

    def is_detail_url(self, href: str) -> bool:
        return "/to-rent/details/" in href
