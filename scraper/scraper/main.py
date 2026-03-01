import asyncio
import logging
import random
from pathlib import Path
import nodriver
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import settings
from . import db
from .sheets import sync_sheet_to_db, update_sold_on_sheet, append_property_to_sheet
from .scrapers.domain_api import scrape_domain
from .scrapers.rea import scrape_rea
from .diff import diff_snapshots
from .notify import notify_pushover
from .images import download_and_cache_images

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("nodriver").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Resolve image directory: env var > default relative to project root
_project_root = Path(__file__).resolve().parent.parent.parent
IMAGE_DIR = Path(settings.image_dir) if settings.image_dir else _project_root / "data" / "images"


def _extract_address(raw_data: dict, source: str) -> str | None:
    """Try to extract a full address from scraped raw_data."""
    if source == "rea":
        details = raw_data.get("details", {})
        listing = details.get("listing", raw_data)
        address = listing.get("address", {})
        if isinstance(address, dict):
            # Try display variants
            display = address.get("display", {})
            if isinstance(display, dict):
                full = display.get("fullAddress") or display.get("shortAddress")
                if full:
                    return full
            elif isinstance(display, str) and display:
                return display
            # Construct from parts
            parts = [
                address.get("streetAddress", ""),
                address.get("suburb", ""),
                address.get("state", ""),
                address.get("postcode", ""),
            ]
            addr = ", ".join(p for p in parts[:2] if p)
            suffix = " ".join(p for p in parts[2:] if p)
            if addr and suffix:
                return f"{addr} {suffix}"
            if addr:
                return addr
    elif source == "domain":
        props = raw_data.get("props", {})
        page_props = props.get("pageProps", {})
        cp = page_props.get("componentProps", {})
        summary = cp.get("listingSummary", {})
        if summary.get("address"):
            return summary["address"]
        addr = cp.get("address") or summary.get("displayAddress")
        if isinstance(addr, str) and addr:
            return addr
    return None


async def _process_url(prop, url, snapshot):
    """Diff against previous snapshot, save changes, notify."""
    prev = await db.get_snapshot(prop.id, url)
    changes = []
    if prev and not snapshot.fetch_error:
        changes = diff_snapshots(prev, snapshot)
        if changes:
            logger.info(
                f"Changes detected for {prop.address} ({url}): "
                f"{[c.field for c in changes]}"
            )
            await db.save_changes(prop.id, url, changes)
            await notify_pushover(prop, changes)

    if not snapshot.fetch_error:
        await db.upsert_snapshot(prop.id, snapshot)
        if snapshot.raw_data:
            try:
                await download_and_cache_images(
                    prop.id, snapshot.raw_data, snapshot.source, IMAGE_DIR
                )
            except Exception as e:
                logger.warning(f"Image caching failed for {prop.address}: {e}")

        # Fill in property details from scrape (for web-added stubs)
        if not prop.sheet_row:
            await _backfill_property(prop, snapshot)

        # Write sold details back to sheet if empty
        await _sync_sold_to_sheet(prop, snapshot)

    await db.update_last_checked(prop.id)
    return len(changes)


async def _backfill_property(prop, snapshot):
    """Update a web-added property with data from a successful scrape, and add to sheet."""
    address = None
    if snapshot.raw_data:
        address = _extract_address(snapshot.raw_data, snapshot.source)

    beds = snapshot.bedrooms
    baths = snapshot.bathrooms
    cars = snapshot.parking
    details = ",".join(str(v) for v in [beds, baths, cars] if v is not None) or None
    price = snapshot.price or None

    if not address and not details and not price:
        return

    await db.backfill_property(prop.id, address, details, price)
    if address:
        logger.info(f"Backfilled address for {prop.id}: {address}")

    # Append to Google Sheet and record the sheet_row
    try:
        sheet_row = append_property_to_sheet(
            address or prop.address,
            details or prop.details or "",
            price or prop.advertised_price or "",
            prop.url,
        )
        await db.set_sheet_row(prop.id, sheet_row)
    except Exception as e:
        logger.warning(f"Failed to append {prop.id} to sheet: {e}")


async def _sync_sold_to_sheet(prop, snapshot):
    """If snapshot shows sold info and the property is missing it, update DB + sheet."""
    is_sold = "sold" in (snapshot.status or "").lower()
    if not is_sold:
        return

    sold_price = snapshot.price if not prop.sold_price else ""
    sold_date = snapshot.sold_date if not prop.sold_date else ""

    if not sold_price and not sold_date:
        return

    # Always update DB
    await db.update_sold_details(prop.id, sold_price, sold_date)
    logger.info(f"Updated sold details for {prop.address}: price={sold_price!r}, date={sold_date!r}")

    # Write to sheet only if this property came from the sheet
    if prop.sheet_row:
        try:
            update_sold_on_sheet(prop.sheet_row, sold_price, sold_date)
        except Exception as e:
            logger.warning(f"Failed to update sheet sold details for {prop.address}: {e}")


async def scrape_all():
    logger.info("Starting scrape cycle")

    try:
        properties = await sync_sheet_to_db()
    except Exception as e:
        logger.error(f"Failed to sync sheet: {e}")
        return

    # Also pick up properties added via the web UI
    try:
        web_properties = await db.get_web_added_properties()
        if web_properties:
            logger.info(f"Including {len(web_properties)} web-added properties")
            properties = properties + web_properties
    except Exception as e:
        logger.warning(f"Failed to fetch web-added properties: {e}")

    total_changes = 0
    errors = 0

    # Collect URLs grouped by site
    domain_jobs = []  # (prop, url)
    rea_jobs = []
    for prop in properties:
        for url in [prop.url, prop.url2]:
            if not url:
                continue
            if "domain.com.au" in url:
                domain_jobs.append((prop, url))
            elif "realestate.com.au" in url:
                rea_jobs.append((prop, url))

    # --- Domain: curl_cffi, light rate limiting ---
    domain_ok = 0
    domain_fail = 0
    logger.info(f"--- Domain: scraping {len(domain_jobs)} URLs ---")
    for i, (prop, url) in enumerate(domain_jobs, 1):
        try:
            snapshot = await scrape_domain(url)
            if snapshot.fetch_error:
                domain_fail += 1
                errors += 1
                logger.error(f"  FAIL [{i}/{len(domain_jobs)}] {prop.address} — {snapshot.fetch_error}")
            else:
                domain_ok += 1
                total_changes += await _process_url(prop, url, snapshot)
                logger.info(f"  OK   [{i}/{len(domain_jobs)}] {prop.address} — {snapshot.price or 'no price'}")
        except Exception as e:
            domain_fail += 1
            errors += 1
            logger.error(f"  FAIL [{i}/{len(domain_jobs)}] {prop.address} — {e}")
        await asyncio.sleep(random.uniform(1, 3))
    logger.info(f"--- Domain done: {domain_ok} ok, {domain_fail} failed ---")

    # --- REA: nodriver (real Chrome), heavier rate limiting ---
    rea_ok = 0
    rea_fail = 0
    if rea_jobs:
        logger.info(f"--- REA: scraping {len(rea_jobs)} URLs ---")
        rea_browser = None
        try:
            rea_browser = await nodriver.start(headless=False)
        except Exception as e:
            logger.error(f"Failed to launch browser for REA: {e}")

        for i, (prop, url) in enumerate(rea_jobs, 1):
            try:
                snapshot = await scrape_rea(url, browser=rea_browser)
                if snapshot.fetch_error:
                    rea_fail += 1
                    errors += 1
                    logger.error(f"  FAIL [{i}/{len(rea_jobs)}] {prop.address} — {snapshot.fetch_error}")
                else:
                    rea_ok += 1
                    total_changes += await _process_url(prop, url, snapshot)
                    logger.info(f"  OK   [{i}/{len(rea_jobs)}] {prop.address} — {snapshot.price or 'no price'}")
            except Exception as e:
                rea_fail += 1
                errors += 1
                logger.error(f"  FAIL [{i}/{len(rea_jobs)}] {prop.address} — {e}")
            delay = random.uniform(settings.rea_delay_min, settings.rea_delay_max)
            logger.info(f"  ... waiting {delay:.0f}s before next REA request")
            await asyncio.sleep(delay)

        if rea_browser:
            rea_browser.stop()
        logger.info(f"--- REA done: {rea_ok} ok, {rea_fail} failed ---")

    logger.info(
        f"=== Scrape cycle complete: {len(properties)} properties, "
        f"{domain_ok + rea_ok} scraped, {errors} errors, "
        f"{total_changes} changes detected ==="
    )


async def async_main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scrape_all,
        "interval",
        hours=settings.scrape_interval_hours,
        id="scrape_all",
    )
    scheduler.start()

    logger.info(
        f"Scraper started. Running every {settings.scrape_interval_hours} hours."
    )

    await scrape_all()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("Shutting down...")
        scheduler.shutdown()
        await db.close_pool()


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
