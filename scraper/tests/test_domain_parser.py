from scraper.scrapers.domain_api import parse_domain_page_data


MOCK_NEXT_DATA = {
    "props": {
        "pageProps": {
            "listingDetails": {
                "status": "Active",
                "propertyDetails": {
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "carspaces": 1,
                },
                "priceDetails": {
                    "displayPrice": "$1,200,000",
                },
                "description": "A stunning family home in a prime location.",
                "advertiserIdentifiers": {
                    "contactName": "John Smith",
                    "agencyName": "Ray White",
                },
                "auctionSchedule": {
                    "time": "2026-03-15T10:30:00",
                },
                "media": [
                    {"url": "img1.jpg"},
                    {"url": "img2.jpg"},
                ],
            }
        }
    }
}


def test_parse_basic_fields():
    snapshot = parse_domain_page_data(
        MOCK_NEXT_DATA,
        "https://www.domain.com.au/5-smith-st-richmond-vic-3121-12345678",
    )
    assert snapshot.source == "domain"
    assert snapshot.price == "$1,200,000"
    assert snapshot.bedrooms == 3
    assert snapshot.bathrooms == 2
    assert snapshot.parking == 1
    assert snapshot.agent_name == "John Smith"
    assert snapshot.agency_name == "Ray White"
    assert snapshot.photo_count == 2
    assert snapshot.auction_date == "2026-03-15T10:30:00"


def test_parse_missing_fields():
    data = {"props": {"pageProps": {"listingDetails": {"status": "Sold"}}}}
    snapshot = parse_domain_page_data(data, "https://example.com")
    assert snapshot.status == "Sold"
    assert snapshot.bedrooms is None
    assert snapshot.price == ""
    assert snapshot.photo_count == 0


def test_parse_description_truncated():
    data = {
        "props": {
            "pageProps": {
                "listingDetails": {"description": "x" * 1000}
            }
        }
    }
    snapshot = parse_domain_page_data(data, "https://example.com")
    assert len(snapshot.description) == 500


def test_parse_flat_page_props():
    """Test fallback when listing data is directly in pageProps."""
    data = {
        "props": {
            "pageProps": {
                "status": "Active",
                "bedrooms": 4,
                "bathrooms": 3,
                "price": "$900,000",
                "description": "Nice place",
            }
        }
    }
    snapshot = parse_domain_page_data(data, "https://example.com")
    assert snapshot.bedrooms == 4
    assert snapshot.price == "$900,000"
