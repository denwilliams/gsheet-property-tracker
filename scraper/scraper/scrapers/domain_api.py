import json
import re
import logging
from curl_cffi import requests as cffi_requests
from ..models import ListingSnapshot

logger = logging.getLogger(__name__)


def parse_domain_page_data(data: dict, url: str) -> ListingSnapshot:
    """Parse listing data from Domain's __NEXT_DATA__ JSON."""
    props = data.get("props", {})
    page_props = props.get("pageProps", {})
    cp = page_props.get("componentProps", {})

    # Single listing pages put data directly in componentProps
    if cp.get("listingId"):
        listing_summary = cp.get("listingSummary", {})
        price_guide = cp.get("priceGuide", {})
        inspection = cp.get("inspection", {})
        gallery = cp.get("gallery", {})
        agents = price_guide.get("agents", cp.get("agents", []))

        images = gallery.get("slides", gallery.get("images", [])) if isinstance(gallery, dict) else []

        inspection_times = []
        if isinstance(inspection, dict):
            for t in inspection.get("inspectionTimes", []):
                inspection_times.append({
                    "opening": t.get("openingDateTime"),
                    "closing": t.get("closingDateTime"),
                })

        return ListingSnapshot(
            url=url,
            source="domain",
            status=listing_summary.get("status", ""),
            price=cp.get("headline", listing_summary.get("title", "")),
            bedrooms=listing_summary.get("beds"),
            bathrooms=listing_summary.get("baths"),
            parking=listing_summary.get("parking"),
            description=(cp.get("description", "") or "")[:500],
            agent_name=agents[0].get("name", "") if agents else "",
            agency_name=cp.get("agencyName", ""),
            auction_date=None,
            photo_count=len(images),
            open_home_times=inspection_times,
            raw_data=data,
        )

    # Fallback: try old-style listingDetails structure
    listing = page_props.get("listingDetails", page_props.get("listing", page_props))
    prop_details = listing.get("propertyDetails", {}) or {}
    price_details = listing.get("priceDetails", {}) or {}
    advertiser = listing.get("advertiserIdentifiers", {}) or listing.get("advertiser", {}) or {}
    auction = listing.get("auctionSchedule", {}) or listing.get("auctionDetails", {}) or {}
    media = listing.get("media", []) or listing.get("photos", []) or []

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


async def scrape_domain(url: str) -> ListingSnapshot:
    """Scrape a domain.com.au listing page using curl_cffi."""
    try:
        resp = cffi_requests.get(url, impersonate="chrome", timeout=30)
        if resp.status_code >= 400:
            return ListingSnapshot(
                url=url, source="domain",
                fetch_error=f"HTTP {resp.status_code}",
            )

        data = _extract_next_data(resp.text)
        if data is None:
            return ListingSnapshot(
                url=url, source="domain",
                fetch_error="Could not extract __NEXT_DATA__ from page",
            )

        return parse_domain_page_data(data, url)

    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        return ListingSnapshot(url=url, source="domain", fetch_error=str(e))
