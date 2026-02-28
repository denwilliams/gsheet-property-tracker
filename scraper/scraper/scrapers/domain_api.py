import re
import logging
import time
import httpx
from ..config import settings
from ..models import ListingSnapshot

logger = logging.getLogger(__name__)

_cached_token: dict | None = None


def extract_domain_listing_id(url: str) -> str:
    url = url.rstrip("/")
    last_segment = url.split("/")[-1]
    match = re.search(r"(\d+)$", last_segment)
    if match:
        return match.group(1)
    raise ValueError(f"Cannot extract listing ID from URL: {url}")


async def _get_token() -> str:
    global _cached_token
    if _cached_token and _cached_token["expires_at"] > time.time():
        return _cached_token["token"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://auth.domain.com.au/v1/connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.domain_client_id,
                "client_secret": settings.domain_client_secret,
                "scope": "api_listings_read",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    _cached_token = {
        "token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 3600) - 60,
    }
    return _cached_token["token"]


async def scrape_domain(url: str) -> ListingSnapshot:
    listing_id = extract_domain_listing_id(url)
    token = await _get_token()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.domain.com.au/v1/listings/{listing_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

        if resp.status_code == 404:
            return ListingSnapshot(
                url=url, source="domain",
                fetch_error=f"Listing {listing_id} not found (404)",
            )

        resp.raise_for_status()
        data = resp.json()

    prop_details = data.get("propertyDetails", {})
    price_details = data.get("priceDetails", {})
    advertiser = data.get("advertiserIdentifiers", {})
    auction = data.get("auctionSchedule", {})
    media = data.get("media", [])

    return ListingSnapshot(
        url=url,
        source="domain",
        status=data.get("status", ""),
        price=price_details.get("displayPrice", ""),
        bedrooms=prop_details.get("bedrooms"),
        bathrooms=prop_details.get("bathrooms"),
        parking=prop_details.get("carspaces"),
        description=(data.get("description", "") or "")[:500],
        agent_name=advertiser.get("contactName", ""),
        agency_name=advertiser.get("agencyName", ""),
        auction_date=auction.get("time"),
        photo_count=len([m for m in media if m.get("type") == "photo"]),
        open_home_times=[],
        raw_data=data,
    )
