from __future__ import annotations

import re
from datetime import date

from .config import Settings
from .models import FilterDecision, Listing

ANTI_SHARE = re.compile(
    r"\b(studio|bedsit|room in a|shared kitchen|shared bathroom|"
    r"en-suite room|student only|short let|flat share|house share)\b",
    re.IGNORECASE,
)
BAD_FLOOR = re.compile(
    r"\b(ground floor|lower ground|basement|garden flat on ground|semi-basement|level 0)\b",
    re.IGNORECASE,
)
GOOD_FLOOR = re.compile(
    r"\b(first|1st|second|2nd|third|3rd|fourth|4th|top|upper) floor\b",
    re.IGNORECASE,
)
BILLS_INCLUDED = re.compile(r"\b(all bills inc(?:luded)?|bills included)\b", re.IGNORECASE)
EXCLUDES_TAX = re.compile(r"\b(exclud(?:es|ing) council tax|council tax not included)\b", re.I)
APRIL_REJECTED = re.compile(
    r"\b(no|not available (?:until|for)).{0,20}april|april.{0,20}(?:not possible|unavailable)\b",
    re.I,
)


def target_move_in(month_day: str, today: date | None = None) -> date:
    today = today or date.today()
    month, day = map(int, month_day.split("-"))
    candidate = date(today.year, month, day)
    return candidate if candidate >= today else date(today.year + 1, month, day)


def calculate_total(listing: Listing, settings: Settings) -> int:
    search = settings.search
    text = listing.searchable_text
    listing.bills_included = bool(BILLS_INCLUDED.search(text))
    listing.council_tax_included = listing.bills_included and not EXCLUDES_TAX.search(text)

    tax_table = search["council_tax_monthly"]
    borough_rates = tax_table.get(listing.borough.upper(), tax_table["DEFAULT"])
    band = listing.council_tax_band.upper()
    listing.council_tax_cost = 0 if listing.council_tax_included else int(
        borough_rates.get(band, borough_rates["D"])
    )

    if listing.bills_included:
        listing.utilities_cost = 0
    elif listing.epc_rating.upper() in {"A", "B", "C"}:
        listing.utilities_cost = int(search["utilities_epc_a_c"])
    elif listing.epc_rating.upper() in {"D", "E"}:
        listing.utilities_cost = int(search["utilities_epc_d_e"])
    else:
        listing.utilities_cost = int(search["default_utilities"])

    listing.total_monthly_cost = (
        listing.rent_pcm + listing.council_tax_cost + listing.utilities_cost
    )
    listing.borderline = (
        search["max_total_monthly_cost"]
        < listing.total_monthly_cost
        <= search["max_total_monthly_cost"] + search["borderline_buffer"]
    )
    return listing.total_monthly_cost


def evaluate(
    listing: Listing,
    settings: Settings,
    today: date | None = None,
    require_commute: bool = True,
) -> FilterDecision:
    search = settings.search
    text = listing.searchable_text
    if listing.rent_pcm > search["portal_search_max_base_rent"]:
        return FilterDecision(False, "base rent exceeds portal ceiling")
    if listing.bedrooms < search["minimum_bedrooms"] or ANTI_SHARE.search(text):
        return FilterDecision(False, "studio, room share, or short let")
    property_type = listing.property_type.lower()
    if any(value in property_type for value in ("studio", "flat share", "house share", "room")):
        return FilterDecision(False, "disallowed property type")
    if BAD_FLOOR.search(text) and not GOOD_FLOOR.search(text):
        return FilterDecision(False, "ground or basement floor")
    if listing.floor == "Unknown" and not GOOD_FLOOR.search(text):
        return FilterDecision(False, "upper floor not confirmed")
    if listing.outcode not in set(search["allowed_outcodes"]):
        return FilterDecision(False, "outside configured London zones")
    if APRIL_REJECTED.search(text):
        return FilterDecision(False, "explicitly rejects April move-in")

    listing.priority = listing.outcode in set(search["priority_outcodes"])
    if require_commute and (not listing.commute_a or not listing.commute_b):
        return FilterDecision(False, "commute unavailable")
    if listing.commute_a and listing.commute_b:
        for label, commute in (
            ("Oxford Circus", listing.commute_a),
            ("Shoreditch", listing.commute_b),
        ):
            if commute.minutes <= search["max_commute_minutes"]:
                continue
            battersea_exception = (
                listing.outcode == "SW11"
                and commute.minutes <= search["battersea_max_commute_minutes"]
                and re.search(r"\b(overground|victoria)\b", commute.summary, re.I)
            )
            if not battersea_exception:
                return FilterDecision(False, f"{label} commute too long")

    total = calculate_total(listing, settings)
    if total > search["max_total_monthly_cost"] + search["borderline_buffer"]:
        return FilterDecision(False, "estimated total cost too high")
    return FilterDecision(True)
