from datetime import date

from pisorentbot.config import load_settings
from pisorentbot.filtering import evaluate
from pisorentbot.models import Commute, Listing, Portal
from pisorentbot.store import fingerprint


def listing(**overrides):
    values = {
        "portal": Portal.OPENRENT,
        "portal_listing_id": "123",
        "url": "https://example.test/123",
        "title": "Mare Street one bedroom flat",
        "description": "First floor flat",
        "rent_pcm": 1250,
        "bedrooms": 1,
        "property_type": "Flat",
        "postcode": "E8 1AA",
        "street": "10 Mare Street",
        "borough": "Hackney",
        "council_tax_band": "A",
        "epc_rating": "C",
        "commute_a": Commute(30),
        "commute_b": Commute(15),
    }
    values.update(overrides)
    return Listing(**values)


def test_accepts_priority_flat_within_true_cost():
    item = listing()
    decision = evaluate(item, load_settings(), today=date(2026, 10, 15))
    assert decision.accepted
    assert item.priority
    assert item.total_monthly_cost == 1484


def test_rejects_disguised_room_and_ground_floor():
    settings = load_settings()
    room = listing(description="Lovely en-suite room near transport")
    ground = listing(description="Ground floor garden flat")
    assert not evaluate(room, settings).accepted
    assert not evaluate(ground, settings).accepted


def test_explicit_upper_floor_overrides_ground_reference():
    item = listing(description="First floor flat above a ground floor shop")
    assert evaluate(item, load_settings()).accepted


def test_rejects_listing_without_proven_upper_floor():
    item = listing(description="One bedroom flat near station")
    assert not evaluate(item, load_settings()).accepted


def test_battersea_commute_exception_requires_named_direct_route():
    settings = load_settings()
    indirect = listing(
        postcode="SW11 1AA",
        borough="Wandsworth",
        commute_a=Commute(42, "Bus and train"),
    )
    direct = listing(
        postcode="SW11 1AA",
        borough="Wandsworth",
        commute_a=Commute(42, "Walk to Victoria line"),
    )
    assert not evaluate(indirect, settings).accepted
    assert evaluate(direct, settings).accepted


def test_bills_included_skips_utilities_and_tax():
    item = listing(rent_pcm=1495, description="First floor, all bills included")
    assert evaluate(item, load_settings()).accepted
    assert item.total_monthly_cost == 1495


def test_availability_after_target_is_accepted():
    item = listing(available_from=date(2027, 5, 1))
    assert evaluate(item, load_settings(), today=date(2026, 10, 15)).accepted


def test_cross_portal_fingerprint_rounds_rent():
    left = listing(rent_pcm=1260)
    right = listing(portal=Portal.RIGHTMOVE, rent_pcm=1261)
    assert fingerprint(left) == fingerprint(right)
