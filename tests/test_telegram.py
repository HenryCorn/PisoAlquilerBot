from test_filtering import listing

from pisorentbot.models import Commute
from pisorentbot.telegram import render_card


def test_card_is_html_safe_and_has_required_fields():
    item = listing(title="<Mare & Street>", furnishing="Part-Furnished", floor="2nd Floor")
    item.commute_a = Commute(24, "Walk & Tube")
    item.commute_b = Commute(14, "Overground")
    item.total_monthly_cost = 1484
    item.council_tax_cost = 104
    item.utilities_cost = 130
    item.crime_score = 41
    item.description += " with balcony and washing machine"
    item.merged_urls = {"OpenRent": item.url}
    card = render_card(item, 1)
    assert "&lt;Mare &amp; Street&gt;" in card
    assert "Part-Furnished" in card
    assert "2nd Floor" in card
    assert "24m" in card and "14m" in card
    assert "🟡 41/100" in card
    assert "Balcony" in card and "Washer" in card
