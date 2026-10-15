from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class Portal(StrEnum):
    OPENRENT = "OpenRent"
    RIGHTMOVE = "Rightmove"
    ZOOPLA = "Zoopla"


@dataclass(slots=True)
class Commute:
    minutes: int
    summary: str = ""


@dataclass(slots=True)
class Listing:
    portal: Portal
    portal_listing_id: str
    url: str
    title: str
    description: str
    rent_pcm: int
    bedrooms: int
    property_type: str = ""
    postcode: str = ""
    street: str = ""
    borough: str = ""
    council_tax_band: str = ""
    furnishing: str = "Unknown"
    floor: str = "Unknown"
    epc_rating: str = ""
    available_from: date | None = None
    availability_text: str = ""
    deposit: int | None = None
    area_sqm: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    key_features: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    image_alt_texts: list[str] = field(default_factory=list)
    bills_included: bool = False
    council_tax_included: bool = False
    commute_a: Commute | None = None
    commute_b: Commute | None = None
    total_monthly_cost: int | None = None
    council_tax_cost: int = 0
    utilities_cost: int = 0
    borderline: bool = False
    priority: bool = False
    merged_urls: dict[str, str] = field(default_factory=dict)
    merged_ids: dict[str, str] = field(default_factory=dict)

    @property
    def outcode(self) -> str:
        return self.postcode.strip().upper().split()[0] if self.postcode else ""

    @property
    def searchable_text(self) -> str:
        return " ".join([self.title, self.description, *self.key_features]).lower()


@dataclass(frozen=True, slots=True)
class FilterDecision:
    accepted: bool
    reason: str = ""
