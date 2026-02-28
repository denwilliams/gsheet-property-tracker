import asyncio
import json
import re
import logging
import nodriver
from ..models import ListingSnapshot

logger = logging.getLogger(__name__)


def parse_rea_page_data(data: dict, url: str) -> ListingSnapshot:
    # Data lives under details.listing in the ArgonautExchange structure
    details = data.get("details", {})
    listing = details.get("listing", data)

    general = listing.get("generalFeatures", {})
    price_info = listing.get("price", {})
    listers = listing.get("listers", [])
    company = listing.get("listingCompany", {})
    media = listing.get("media", {})
    images = media.get("images", []) if isinstance(media, dict) else []

    return ListingSnapshot(
        url=url,
        source="rea",
        status=listing.get("status", ""),
        price=price_info.get("display", "") if isinstance(price_info, dict) else "",
        bedrooms=general.get("bedrooms", {}).get("value") if isinstance(general.get("bedrooms"), dict) else None,
        bathrooms=general.get("bathrooms", {}).get("value") if isinstance(general.get("bathrooms"), dict) else None,
        parking=general.get("parkingSpaces", {}).get("value") if isinstance(general.get("parkingSpaces"), dict) else None,
        description=(listing.get("description", "") or "")[:500],
        agent_name=listers[0].get("name", "") if listers else "",
        agency_name=company.get("name", "") if isinstance(company, dict) else "",
        auction_date=None,
        photo_count=len(images),
        open_home_times=[],
        raw_data=data,
    )


def _extract_listing_data(html: str) -> dict | None:
    match = re.search(r'window\.ArgonautExchange\s*=\s*(\{.+?\});', html, re.DOTALL)
    if match:
        try:
            outer = json.loads(match.group(1))
            cache_key = "resi-property_listing-experience-web"
            if cache_key in outer:
                mid = json.loads(outer[cache_key].get("urqlClientCache", "{}"))
                for value in mid.values():
                    if "data" in value:
                        return json.loads(value["data"])
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse ArgonautExchange: {e}")

    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


async def scrape_rea(url: str, browser=None) -> ListingSnapshot:
    """Scrape a realestate.com.au listing page using nodriver."""
    should_close = browser is None

    try:
        if browser is None:
            browser = await nodriver.start(headless=True)

        page = await browser.get(url)

        # Wait for Kasada challenge to resolve and page to load
        for _ in range(10):
            await asyncio.sleep(2)
            html = await page.get_content()
            if "ArgonautExchange" in html or "__NEXT_DATA__" in html:
                break
        else:
            html = await page.get_content()

        data = _extract_listing_data(html)
        if data is None:
            if "KPSDK" in html:
                return ListingSnapshot(
                    url=url, source="rea",
                    fetch_error="Blocked by bot protection (Kasada)",
                )
            return ListingSnapshot(
                url=url, source="rea",
                fetch_error="Could not extract listing data from page",
            )

        return parse_rea_page_data(data, url)

    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        return ListingSnapshot(url=url, source="rea", fetch_error=str(e))

    finally:
        if should_close and browser:
            browser.stop()
