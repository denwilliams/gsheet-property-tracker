from .models import ListingSnapshot, Change

TRACKED_FIELDS = [
    "status", "price", "bedrooms", "bathrooms", "parking",
    "description", "agent_name", "agency_name", "auction_date",
    "photo_count", "sold_date",
]


def diff_snapshots(old: ListingSnapshot, new: ListingSnapshot) -> list[Change]:
    changes = []
    for field in TRACKED_FIELDS:
        old_val = str(getattr(old, field) or "")
        new_val = str(getattr(new, field) or "")
        if old_val != new_val:
            changes.append(Change(field=field, old_value=old_val, new_value=new_val))
    return changes
