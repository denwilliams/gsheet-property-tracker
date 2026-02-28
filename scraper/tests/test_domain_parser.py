from scraper.scrapers.domain_api import extract_domain_listing_id


def test_extract_full_url():
    url = "https://www.domain.com.au/5401-63-la-trobe-street-melbourne-vic-3000-2018796388"
    assert extract_domain_listing_id(url) == "2018796388"


def test_extract_short_url():
    url = "https://www.domain.com.au/12500140"
    assert extract_domain_listing_id(url) == "12500140"


def test_extract_with_trailing_slash():
    url = "https://www.domain.com.au/5-smith-st-richmond-vic-3121-12345678/"
    assert extract_domain_listing_id(url) == "12345678"
