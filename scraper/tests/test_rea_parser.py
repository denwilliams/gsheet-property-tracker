from scraper.scrapers.rea import parse_rea_page_data

# Mock data matching the real ArgonautExchange structure: details.listing.{fields}
MOCK_LISTING_DATA = {
    "details": {
        "listing": {
            "status": "Buy",
            "price": {"display": "$800,000 - $880,000"},
            "generalFeatures": {
                "bedrooms": {"value": 3},
                "bathrooms": {"value": 2},
                "parkingSpaces": {"value": 2},
            },
            "description": "A beautiful family home with a spacious backyard.",
            "listers": [{"name": "Jane Smith"}],
            "listingCompany": {"name": "McGrath"},
            "media": {"images": [{"uri": "img1.jpg"}, {"uri": "img2.jpg"}, {"uri": "img3.jpg"}]},
        }
    }
}


def test_parse_basic_fields():
    snapshot = parse_rea_page_data(MOCK_LISTING_DATA, "https://www.realestate.com.au/property-house-vic-test-123")
    assert snapshot.source == "rea"
    assert snapshot.price == "$800,000 - $880,000"
    assert snapshot.bedrooms == 3
    assert snapshot.bathrooms == 2
    assert snapshot.parking == 2
    assert snapshot.agent_name == "Jane Smith"
    assert snapshot.agency_name == "McGrath"
    assert snapshot.photo_count == 3


def test_parse_missing_fields():
    data = {"details": {"listing": {"status": "Sold"}}}
    snapshot = parse_rea_page_data(data, "https://example.com")
    assert snapshot.status == "Sold"
    assert snapshot.bedrooms is None
    assert snapshot.price == ""
    assert snapshot.photo_count == 0


def test_parse_description_truncated():
    data = {"details": {"listing": {"description": "x" * 1000}}}
    snapshot = parse_rea_page_data(data, "https://example.com")
    assert len(snapshot.description) == 500


def test_parse_flat_fallback():
    """If data doesn't have details.listing, falls back to top-level keys."""
    data = {
        "status": "Buy",
        "price": {"display": "$500,000"},
        "generalFeatures": {"bedrooms": {"value": 2}},
        "listers": [],
        "listingCompany": {"name": "Agency"},
        "media": {"images": []},
    }
    snapshot = parse_rea_page_data(data, "https://example.com")
    assert snapshot.price == "$500,000"
    assert snapshot.bedrooms == 2
