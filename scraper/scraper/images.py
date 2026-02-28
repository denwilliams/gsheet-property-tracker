import hashlib
import logging
import re
from pathlib import Path

import httpx

from . import db

logger = logging.getLogger(__name__)


def extract_image_urls(raw_data: dict, source: str) -> list[str]:
    """Extract image URLs from raw listing data."""
    urls: list[str] = []

    if source == "rea":
        urls = _extract_rea_images(raw_data)
    elif source == "domain":
        urls = _extract_domain_images(raw_data)

    return urls


def _extract_rea_images(data: dict) -> list[str]:
    """Extract image URLs from REA ArgonautExchange data."""
    details = data.get("details", {})
    listing = details.get("listing", data)
    media = listing.get("media", {})
    images = media.get("images", []) if isinstance(media, dict) else []

    urls = []
    for img in images:
        if isinstance(img, dict):
            uri = img.get("templatedUrl", img.get("uri", ""))
        elif isinstance(img, str):
            uri = img
        else:
            continue
        if not uri:
            continue
        # REA uses templated URLs like "https://.../{size}/..."
        uri = re.sub(r"\{size\}", "800x600", uri)
        urls.append(uri)

    return urls


def _extract_domain_images(data: dict) -> list[str]:
    """Extract image URLs from Domain __NEXT_DATA__."""
    props = data.get("props", {})
    page_props = props.get("pageProps", {})
    cp = page_props.get("componentProps", {})

    # Primary path: gallery.slides
    gallery = cp.get("gallery", {})
    slides = gallery.get("slides", []) if isinstance(gallery, dict) else []

    urls = []
    for slide in slides:
        if isinstance(slide, dict):
            url = slide.get("url", slide.get("src", ""))
        elif isinstance(slide, str):
            url = slide
        else:
            continue
        if url:
            urls.append(url)

    if urls:
        return urls

    # Fallback: old-style media list
    listing = page_props.get("listingDetails", page_props.get("listing", {}))
    media = listing.get("media", []) or listing.get("photos", []) or []
    if isinstance(media, dict):
        media = media.get("images", []) or media.get("photos", []) or []

    for item in media:
        if isinstance(item, dict):
            url = item.get("url", item.get("src", ""))
        elif isinstance(item, str):
            url = item
        else:
            continue
        if url:
            urls.append(url)

    return urls


def url_to_filename(url: str) -> str:
    """Convert a URL to a deterministic filename via SHA-256 hash."""
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"{h}.jpg"


async def download_and_cache_images(
    property_id: str,
    raw_data: dict,
    source: str,
    image_dir: Path,
) -> int:
    """Download missing images and upsert DB rows. Returns count of new images."""
    urls = extract_image_urls(raw_data, source)
    if not urls:
        return 0

    prop_dir = image_dir / property_id
    prop_dir.mkdir(parents=True, exist_ok=True)

    pool = await db.get_pool()
    new_count = 0

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for order, url in enumerate(urls):
            filename = url_to_filename(url)
            filepath = prop_dir / filename

            # Skip if file already exists on disk
            if filepath.exists():
                # Still upsert the DB row in case it was lost
                await _upsert_image_row(pool, property_id, url, filename, order, source)
                continue

            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"Image HTTP {resp.status_code}: {url[:80]}")
                    continue

                filepath.write_bytes(resp.content)
                await _upsert_image_row(pool, property_id, url, filename, order, source)
                new_count += 1
            except Exception as e:
                logger.warning(f"Failed to download image: {e}")

    if new_count:
        logger.info(f"Cached {new_count} new images for {property_id}")

    return new_count


async def _upsert_image_row(pool, property_id, url, filename, display_order, source):
    await pool.execute(
        """
        INSERT INTO property_images (property_id, url, filename, display_order, source)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (property_id, filename) DO UPDATE SET
            url = EXCLUDED.url,
            display_order = EXCLUDED.display_order
        """,
        property_id, url, filename, display_order, source,
    )
