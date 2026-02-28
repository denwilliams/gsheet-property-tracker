import asyncio
import logging
import random
import nodriver
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import settings
from . import db
from .sheets import sync_sheet_to_db
from .scrapers.domain_api import scrape_domain
from .scrapers.rea import scrape_rea
from .diff import diff_snapshots
from .notify import notify_pushover

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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

    await db.update_last_checked(prop.id)
    return len(changes)


async def scrape_all():
    logger.info("Starting scrape cycle")

    try:
        properties = await sync_sheet_to_db()
    except Exception as e:
        logger.error(f"Failed to sync sheet: {e}")
        return

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
    logger.info(f"Scraping {len(domain_jobs)} Domain URLs")
    for prop, url in domain_jobs:
        try:
            snapshot = await scrape_domain(url)
            if snapshot.fetch_error:
                logger.warning(f"Fetch error for {url}: {snapshot.fetch_error}")
                errors += 1
            else:
                total_changes += await _process_url(prop, url, snapshot)
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            errors += 1
        await asyncio.sleep(random.uniform(1, 3))

    # --- REA: nodriver (real Chrome), heavier rate limiting ---
    if rea_jobs:
        logger.info(f"Scraping {len(rea_jobs)} REA URLs")
        rea_browser = None
        try:
            rea_browser = await nodriver.start(headless=True)
        except Exception as e:
            logger.warning(f"Failed to launch nodriver browser: {e}")

        for prop, url in rea_jobs:
            try:
                snapshot = await scrape_rea(url, browser=rea_browser)
                if snapshot.fetch_error:
                    logger.warning(f"Fetch error for {url}: {snapshot.fetch_error}")
                    errors += 1
                else:
                    total_changes += await _process_url(prop, url, snapshot)
            except Exception as e:
                logger.error(f"Error processing {url}: {e}")
                errors += 1
            delay = random.uniform(settings.rea_delay_min, settings.rea_delay_max)
            logger.debug(f"Waiting {delay:.0f}s before next REA request")
            await asyncio.sleep(delay)

        if rea_browser:
            rea_browser.stop()

    logger.info(
        f"Scrape cycle complete: {len(properties)} properties, "
        f"{total_changes} changes detected, {errors} errors"
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
