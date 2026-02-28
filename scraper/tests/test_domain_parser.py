from scraper.scrapers.domain_api import parse_domain_page_data


# New-style Domain data: componentProps with listingId
MOCK_COMPONENT_PROPS_DATA = {
    "props": {
        "pageProps": {
            "componentProps": {
                "listingId": "2020091729",
                "headline": "Contact Agent",
                "description": "A stunning family home in a prime location.",
                "agencyName": "Ray White",
                "listingSummary": {
                    "status": "live",
                    "beds": 3,
                    "baths": 2,
                    "parking": 1,
                    "title": "Contact Agent",
                },
                "priceGuide": {
                    "agents": [{"name": "John Smith"}],
                },
                "gallery": {
                    "images": [{"url": "img1.jpg"}, {"url": "img2.jpg"}],
                },
                "inspection": {
                    "inspectionTimes": [
                        {
                            "openingDateTime": "2026-03-01T11:30:00",
                            "closingDateTime": "2026-03-01T12:15:00",
                        }
                    ],
                },
            }
        }
    }
}


# Old-style Domain data: listingDetails
MOCK_LISTING_DETAILS_DATA = {
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


def test_parse_component_props():
    snapshot = parse_domain_page_data(
        MOCK_COMPONENT_PROPS_DATA,
        "https://www.domain.com.au/rouse-hill-nsw-2155-2020091729",
    )
    assert snapshot.source == "domain"
    assert snapshot.price == "Contact Agent"
    assert snapshot.bedrooms == 3
    assert snapshot.bathrooms == 2
    assert snapshot.parking == 1
    assert snapshot.agent_name == "John Smith"
    assert snapshot.agency_name == "Ray White"
    assert snapshot.photo_count == 2
    assert len(snapshot.open_home_times) == 1
    assert snapshot.status == "live"


def test_parse_listing_details_fallback():
    snapshot = parse_domain_page_data(
        MOCK_LISTING_DETAILS_DATA,
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
