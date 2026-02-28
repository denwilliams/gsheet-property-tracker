from scraper.db import property_id
from scraper.models import Property, ListingSnapshot, Change


def test_property_id_deterministic():
    assert property_id("12 Smith St, Northcote") == property_id("12 Smith St, Northcote")


def test_property_id_case_insensitive():
    assert property_id("12 Smith St") == property_id("12 smith st")


def test_property_id_strips_whitespace():
    assert property_id("  12 Smith St  ") == property_id("12 Smith St")


def test_listing_snapshot_defaults():
    s = ListingSnapshot(url="http://example.com", source="domain")
    assert s.price == ""
    assert s.bedrooms is None
    assert s.open_home_times == []
    assert s.fetch_error is None


def test_change_creation():
    c = Change(field="price", old_value="$500K", new_value="$520K")
    assert c.field == "price"
