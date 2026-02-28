import json
import logging
from playwright.async_api import async_playwright
from ..models import ListingSnapshot

logger = logging.getLogger(__name__)


def parse_domain_page_data(data: dict, url: str) -> ListingSnapshot:
    """Parse listing data from Domain's __NEXT_DATA__ JSON into a ListingSnapshot."""
    # Domain's __NEXT_DATA__ nests listing info in various structures.
    # Try to navigate common paths.
    listing = data
    props = data.get("props", {})
    page_props = props.get("pageProps", {})

    # The listing data may be under pageProps directly or nested further
    if "listingDetails" in page_props:
        listing = page_props["listingDetails"]
    elif "listing" in page_props:
        listing = page_props["listing"]
    elif page_props:
        listing = page_props

    # Extract fields with defensive access
    prop_details = listing.get("propertyDetails", {}) or {}
    price_details = listing.get("priceDetails", {}) or {}
    advertiser = listing.get("advertiserIdentifiers", {}) or listing.get("advertiser", {}) or {}
    auction = listing.get("auctionSchedule", {}) or listing.get("auctionDetails", {}) or {}
    media = listing.get("media", []) or listing.get("photos", []) or []

    # Handle both list and dict media formats
    if isinstance(media, list):
        photo_count = len(media)
    elif isinstance(media, dict):
        photo_count = len(media.get("images", []) or media.get("photos", []) or [])
    else:
        photo_count = 0

    return ListingSnapshot(
        url=url,
        source="domain",
        status=listing.get("status", listing.get("listingType", "")),
        price=price_details.get("displayPrice", listing.get("price", "")),
        bedrooms=prop_details.get("bedrooms") or listing.get("bedrooms"),
        bathrooms=prop_details.get("bathrooms") or listing.get("bathrooms"),
        parking=prop_details.get("carspaces") or listing.get("carspaces"),
        description=(listing.get("description", "") or "")[:500],
        agent_name=advertiser.get("contactName", advertiser.get("name", "")),
        agency_name=advertiser.get("agencyName", advertiser.get("agency", "")),
        auction_date=auction.get("time", auction.get("dateTime")),
        photo_count=photo_count,
        open_home_times=[],
        raw_data=data,
    )


def _extract_next_data(html: str) -> dict | None:
    """Extract __NEXT_DATA__ JSON from a Domain.com.au page."""
    import re
    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>',
        html,
        re.DOTALL,
    )
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse __NEXT_DATA__: {e}")
    return None


async def scrape_domain(url: str, browser=None) -> ListingSnapshot:
    """Scrape a domain.com.au listing page using Playwright."""
    should_close = browser is None

    try:
        if browser is None:
            pw = await async_playwright().__aenter__()
            browser = await pw.chromium.launch(headless=True)

        context = await browser.new_context(
            locale="en-AU",
            timezone_id="Australia/Sydney",
        )
        page = await context.new_page()

        try:
            from playwright_stealth import stealth_async
            await stealth_async(page)
        except ImportError:
            pass

        response = await page.goto(url, wait_until="networkidle", timeout=30000)
        if response and response.status >= 400:
            await context.close()
            return ListingSnapshot(
                url=url, source="domain",
                fetch_error=f"HTTP {response.status}",
            )

        html = await page.content()
        await context.close()

        data = _extract_next_data(html)
        if data is None:
            return ListingSnapshot(
                url=url, source="domain",
                fetch_error="Could not extract __NEXT_DATA__ from page",
            )

        return parse_domain_page_data(data, url)

    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        return ListingSnapshot(url=url, source="domain", fetch_error=str(e))

    finally:
        if should_close and browser:
            await browser.close()
