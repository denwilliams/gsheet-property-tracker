import hashlib
import json
import asyncpg
from .config import settings
from .models import Property, ListingSnapshot, Change


_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def property_id(address: str) -> str:
    return hashlib.md5(address.strip().lower().encode()).hexdigest()[:12]


async def upsert_properties(properties: list[Property]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        for p in properties:
            await conn.execute(
                """
                INSERT INTO properties (id, address, details, area, advertised_price,
                    sold_price, sold_date, notes, url, url2, sheet_row, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW())
                ON CONFLICT (id) DO UPDATE SET
                    address=EXCLUDED.address, details=EXCLUDED.details,
                    area=EXCLUDED.area, advertised_price=EXCLUDED.advertised_price,
                    sold_price=EXCLUDED.sold_price, sold_date=EXCLUDED.sold_date,
                    notes=EXCLUDED.notes, url=EXCLUDED.url, url2=EXCLUDED.url2,
                    sheet_row=EXCLUDED.sheet_row, updated_at=NOW()
                """,
                p.id, p.address, p.details, p.area, p.advertised_price,
                p.sold_price, p.sold_date, p.notes, p.url, p.url2, p.sheet_row,
            )


async def get_all_properties() -> list[Property]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM properties ORDER BY address")
    return [
        Property(
            id=r["id"], address=r["address"], details=r["details"] or "",
            area=r["area"] or "", advertised_price=r["advertised_price"] or "",
            sold_price=r["sold_price"] or "", sold_date=r["sold_date"] or "",
            notes=r["notes"] or "", url=r["url"] or "", url2=r["url2"] or "",
            sheet_row=r["sheet_row"] or 0,
        )
        for r in rows
    ]


async def get_snapshot(property_id: str, url: str) -> ListingSnapshot | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM listing_snapshots WHERE property_id=$1 AND url=$2",
        property_id, url,
    )
    if not row:
        return None
    return ListingSnapshot(
        url=row["url"], source=row["source"], status=row["status"] or "",
        price=row["price"] or "", bedrooms=row["bedrooms"],
        bathrooms=row["bathrooms"], parking=row["parking"],
        description=row["description"] or "", agent_name=row["agent_name"] or "",
        agency_name=row["agency_name"] or "",
        auction_date=str(row["auction_date"]) if row["auction_date"] else None,
        photo_count=row["photo_count"] or 0,
        open_home_times=row["open_home_times"] or [],
        raw_data=row["raw_data"], fetch_error=row["fetch_error"],
        sold_date=row["sold_date"] or "",
    )


async def upsert_snapshot(property_id: str, snapshot: ListingSnapshot):
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO listing_snapshots (property_id, url, source, status, price,
            bedrooms, bathrooms, parking, description, agent_name, agency_name,
            auction_date, photo_count, sold_date, open_home_times, raw_data, fetch_error, fetched_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,NOW())
        ON CONFLICT (property_id, url) DO UPDATE SET
            source=EXCLUDED.source, status=EXCLUDED.status, price=EXCLUDED.price,
            bedrooms=EXCLUDED.bedrooms, bathrooms=EXCLUDED.bathrooms,
            parking=EXCLUDED.parking, description=EXCLUDED.description,
            agent_name=EXCLUDED.agent_name, agency_name=EXCLUDED.agency_name,
            auction_date=EXCLUDED.auction_date, photo_count=EXCLUDED.photo_count,
            sold_date=EXCLUDED.sold_date,
            open_home_times=EXCLUDED.open_home_times, raw_data=EXCLUDED.raw_data,
            fetch_error=EXCLUDED.fetch_error, fetched_at=NOW()
        """,
        property_id, snapshot.url, snapshot.source, snapshot.status, snapshot.price,
        snapshot.bedrooms, snapshot.bathrooms, snapshot.parking, snapshot.description,
        snapshot.agent_name, snapshot.agency_name, snapshot.auction_date,
        snapshot.photo_count, snapshot.sold_date, json.dumps(snapshot.open_home_times),
        json.dumps(snapshot.raw_data) if snapshot.raw_data else None,
        snapshot.fetch_error,
    )


async def save_changes(property_id: str, url: str, changes: list[Change]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        for c in changes:
            await conn.execute(
                """
                INSERT INTO changes (property_id, url, field, old_value, new_value)
                VALUES ($1, $2, $3, $4, $5)
                """,
                property_id, url, c.field, c.old_value, c.new_value,
            )


async def update_last_checked(property_id: str):
    pool = await get_pool()
    await pool.execute(
        "UPDATE properties SET last_checked=NOW() WHERE id=$1", property_id
    )
