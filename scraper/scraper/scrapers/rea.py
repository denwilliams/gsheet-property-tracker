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
            browser = await nodriver.start(headless=False)

        logger.info(f"REA: loading {url}")
        page = await browser.get(url)

        # Kasada serves a challenge page then redirects to the real page.
        # Poll for up to 30s, trying to actually extract data each iteration
        # (not just checking for string presence, which gives false positives).
        data = None
        html = ""
        for i in range(15):
            await asyncio.sleep(2)
            elapsed = (i + 1) * 2

            # Get the currently active tab — Kasada may have navigated
            try:
                current = browser.main_tab
                if current:
                    html = await current.get_content()
                else:
                    html = await page.get_content()
            except Exception:
                html = await page.get_content()

            page_len = len(html)
            is_kasada = page_len < 2000 and "KPSDK" in html

            # Try actual extraction (not just string matching)
            data = _extract_listing_data(html)
            if data is not None:
                logger.info(f"REA: OK — extracted data after {elapsed}s")
                break

            # Real page loaded but no listing data (e.g. "off market" page)
            if page_len > 10000 and not is_kasada:
                logger.info(f"REA: page loaded ({page_len} bytes) but no listing data — probably off-market")
                break

            if is_kasada:
                logger.info(f"REA: [{elapsed}s] waiting for Kasada challenge...")
            else:
                logger.info(f"REA: [{elapsed}s] page_len={page_len}, waiting for data...")
        else:
            # Final attempt — try reading the JS variable directly
            logger.info("REA: polling timed out, trying JS evaluation fallback")
            try:
                current = browser.main_tab or page
                result = await current.evaluate(
                    "JSON.stringify(window.ArgonautExchange || null)"
                )
                if result and result != "null":
                    outer = json.loads(result)
                    cache_key = "resi-property_listing-experience-web"
                    if cache_key in outer:
                        mid = json.loads(outer[cache_key].get("urqlClientCache", "{}"))
                        for value in mid.values():
                            if "data" in value:
                                data = json.loads(value["data"])
                                logger.info("REA: OK — got data via JS evaluation fallback")
                                break
            except Exception as e:
                logger.warning(f"REA: JS evaluation fallback failed: {e}")

        if data is None:
            if len(html) < 2000:
                logger.error(f"REA: BLOCKED by Kasada for {url}")
                return ListingSnapshot(
                    url=url, source="rea",
                    fetch_error="Blocked by bot protection (Kasada)",
                )
            logger.warning(f"REA: no listing data for {url} (page may be off-market or removed)")
            return ListingSnapshot(
                url=url, source="rea",
                fetch_error="No listing data (off-market or removed)",
            )

        return parse_rea_page_data(data, url)

    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        return ListingSnapshot(url=url, source="rea", fetch_error=str(e))

    finally:
        if should_close and browser:
            browser.stop()
