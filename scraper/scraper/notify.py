import logging
import httpx
from .config import settings
from .models import Property, Change

logger = logging.getLogger(__name__)


async def notify_pushover(property: Property, changes: list[Change]):
    if not settings.pushover_app_token or not settings.pushover_user_key:
        logger.warning("Pushover not configured, skipping notification")
        return

    message = "\n".join(
        f"{c.field}: {c.old_value} \u2192 {c.new_value}" for c in changes
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.pushover.net/1/messages.json",
                json={
                    "token": settings.pushover_app_token,
                    "user": settings.pushover_user_key,
                    "title": f"Property Update: {property.address}",
                    "message": message,
                    "url": property.url,
                    "url_title": "View Listing",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"Pushover notification sent for {property.address}")
    except Exception as e:
        logger.error(f"Failed to send Pushover notification: {e}")
