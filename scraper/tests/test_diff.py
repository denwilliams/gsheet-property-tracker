from scraper.diff import diff_snapshots
from scraper.models import ListingSnapshot


def _make_snapshot(**overrides) -> ListingSnapshot:
    defaults = dict(url="http://example.com", source="domain", status="for sale",
                    price="$500K", bedrooms=3, bathrooms=2, parking=1,
                    description="Nice house", agent_name="John", agency_name="Ray White",
                    auction_date=None, photo_count=10)
    defaults.update(overrides)
    return ListingSnapshot(**defaults)


def test_no_changes():
    old = _make_snapshot()
    new = _make_snapshot()
    assert diff_snapshots(old, new) == []


def test_price_change():
    old = _make_snapshot(price="$500K")
    new = _make_snapshot(price="$520K")
    changes = diff_snapshots(old, new)
    assert len(changes) == 1
    assert changes[0].field == "price"
    assert changes[0].old_value == "$500K"
    assert changes[0].new_value == "$520K"


def test_multiple_changes():
    old = _make_snapshot(price="$500K", status="for sale")
    new = _make_snapshot(price="$520K", status="under offer")
    changes = diff_snapshots(old, new)
    assert len(changes) == 2
    fields = {c.field for c in changes}
    assert fields == {"price", "status"}


def test_none_to_value():
    old = _make_snapshot(auction_date=None)
    new = _make_snapshot(auction_date="2026-03-15")
    changes = diff_snapshots(old, new)
    assert len(changes) == 1
    assert changes[0].field == "auction_date"


def test_description_change():
    old = _make_snapshot(description="Nice house")
    new = _make_snapshot(description="Nice house with pool")
    changes = diff_snapshots(old, new)
    assert len(changes) == 1
    assert changes[0].field == "description"


def test_photo_count_change():
    old = _make_snapshot(photo_count=10)
    new = _make_snapshot(photo_count=15)
    changes = diff_snapshots(old, new)
    assert len(changes) == 1
    assert changes[0].field == "photo_count"
