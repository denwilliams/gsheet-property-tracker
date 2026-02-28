import asyncio
import logging
import random
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


async def scrape_all():
    logger.info("Starting scrape cycle")

    try:
        properties = await sync_sheet_to_db()
    except Exception as e:
        logger.error(f"Failed to sync sheet: {e}")
        return

    total_changes = 0
    errors = 0

    browser = None
    try:
        from playwright.async_api import async_playwright
        pw = await async_playwright().__aenter__()
        browser = await pw.chromium.launch(headless=True)
    except Exception as e:
        logger.warning(f"Failed to launch browser for scraping: {e}")

    for prop in properties:
        for url in [prop.url, prop.url2]:
            if not url:
                continue

            try:
                if "domain.com.au" in url:
                    snapshot = await scrape_domain(url, browser=browser)
                elif "realestate.com.au" in url:
                    snapshot = await scrape_rea(url, browser=browser)
                else:
                    logger.debug(f"Skipping unknown URL: {url}")
                    continue

                if snapshot.fetch_error:
                    logger.warning(f"Fetch error for {url}: {snapshot.fetch_error}")
                    errors += 1

                prev = await db.get_snapshot(prop.id, url)
                if prev and not snapshot.fetch_error:
                    changes = diff_snapshots(prev, snapshot)
                    if changes:
                        logger.info(
                            f"Changes detected for {prop.address} ({url}): "
                            f"{[c.field for c in changes]}"
                        )
                        await db.save_changes(prop.id, url, changes)
                        await notify_pushover(prop, changes)
                        total_changes += len(changes)

                if not snapshot.fetch_error:
                    await db.upsert_snapshot(prop.id, snapshot)

                await db.update_last_checked(prop.id)

            except Exception as e:
                logger.error(f"Error processing {url}: {e}")
                errors += 1

            delay = random.uniform(settings.rea_delay_min, settings.rea_delay_max)
            await asyncio.sleep(delay)

    if browser:
        await browser.close()

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
