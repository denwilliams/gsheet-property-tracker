import json
import re
import logging
from playwright.async_api import async_playwright
from ..models import ListingSnapshot

logger = logging.getLogger(__name__)


def parse_rea_page_data(data: dict, url: str) -> ListingSnapshot:
    general = data.get("generalFeatures", {})
    price_info = data.get("price", {})
    listers = data.get("listers", [])
    company = data.get("listingCompany", {})
    auction = data.get("auctionDetails")
    media = data.get("media", {})
    images = media.get("images", []) if isinstance(media, dict) else []

    return ListingSnapshot(
        url=url,
        source="rea",
        status=data.get("status", ""),
        price=price_info.get("display", "") if isinstance(price_info, dict) else "",
        bedrooms=general.get("bedrooms", {}).get("value") if isinstance(general.get("bedrooms"), dict) else None,
        bathrooms=general.get("bathrooms", {}).get("value") if isinstance(general.get("bathrooms"), dict) else None,
        parking=general.get("parkingSpaces", {}).get("value") if isinstance(general.get("parkingSpaces"), dict) else None,
        description=(data.get("description", "") or "")[:500],
        agent_name=listers[0].get("name", "") if listers else "",
        agency_name=company.get("name", "") if isinstance(company, dict) else "",
        auction_date=auction.get("dateTime") if isinstance(auction, dict) else None,
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
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(page)
        except Exception:
            logger.warning("playwright-stealth not available, proceeding without stealth")

        response = await page.goto(url, wait_until="networkidle", timeout=30000)
        if response and response.status >= 400:
            await context.close()
            return ListingSnapshot(
                url=url, source="rea",
                fetch_error=f"HTTP {response.status}",
            )

        html = await page.content()
        await context.close()

        data = _extract_listing_data(html)
        if data is None:
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
            await browser.close()
