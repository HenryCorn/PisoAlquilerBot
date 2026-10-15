from test_filtering import listing

from pisorentbot.models import Portal
from pisorentbot.service import merge_listings


def test_merge_prefers_openrent_and_keeps_both_links():
    rightmove = listing(
        portal=Portal.RIGHTMOVE,
        portal_listing_id="rm-1",
        url="https://rightmove.test/1",
    )
    openrent = listing(
        portal=Portal.OPENRENT,
        portal_listing_id="or-1",
        url="https://openrent.test/1",
    )
    merged = merge_listings([rightmove, openrent])
    assert len(merged) == 1
    assert merged[0].portal is Portal.OPENRENT
    assert set(merged[0].merged_urls) == {"OpenRent", "Rightmove"}
