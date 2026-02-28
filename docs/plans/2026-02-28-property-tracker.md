# Property Tracker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a property tracking dashboard that syncs from Google Sheets, scrapes Australian property listings for changes, and displays everything in a nice web UI.

**Architecture:** Two processes on a Raspberry Pi — a Python scraper daemon (APScheduler + Playwright + Domain API) writes to PostgreSQL, and a SvelteKit frontend reads from it. Cloudflare Tunnel for external HTTPS access.

**Tech Stack:** Python 3.12+ (asyncpg, httpx, playwright, gspread, APScheduler), SvelteKit (adapter-node, postgres.js, Tailwind CSS), PostgreSQL 16, Docker Compose.

---

## Task 1: Project Scaffolding + Docker Compose + Database

**Files:**
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `scraper/pyproject.toml`
- Create: `scraper/Dockerfile`
- Create: `scraper/scraper/__init__.py`
- Create: `scraper/scraper/config.py`
- Create: `db/init.sql`

**Step 1: Create `.env.example`**

```bash
# .env.example

# PostgreSQL
POSTGRES_PASSWORD=changeme
DATABASE_URL=postgresql://tracker:changeme@localhost:5432/property_tracker

# Google Sheets
GOOGLE_SERVICE_ACCOUNT_JSON={}
GOOGLE_SHEET_ID=your_sheet_id
GOOGLE_SHEET_RANGE=Sheet1!A:I

# Domain.com.au API
DOMAIN_CLIENT_ID=
DOMAIN_CLIENT_SECRET=

# Pushover
PUSHOVER_APP_TOKEN=
PUSHOVER_USER_KEY=

# Auth
AUTH_EMAIL=you@example.com
AUTH_PASSWORD=changeme

# Scraper
SCRAPE_INTERVAL_HOURS=4
REA_DELAY_MIN=5
REA_DELAY_MAX=15
```

**Step 2: Create `db/init.sql`**

```sql
CREATE TABLE IF NOT EXISTS properties (
    id              TEXT PRIMARY KEY,
    address         TEXT NOT NULL,
    details         TEXT,
    area            TEXT,
    advertised_price TEXT,
    sold_price      TEXT,
    sold_date       TEXT,
    notes           TEXT,
    url             TEXT,
    url2            TEXT,
    last_checked    TIMESTAMPTZ,
    sheet_row       INT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS listing_snapshots (
    id              SERIAL PRIMARY KEY,
    property_id     TEXT REFERENCES properties(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    source          TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT,
    price           TEXT,
    bedrooms        INT,
    bathrooms       INT,
    parking         INT,
    description     TEXT,
    agent_name      TEXT,
    agency_name     TEXT,
    auction_date    TIMESTAMPTZ,
    photo_count     INT,
    open_home_times JSONB DEFAULT '[]',
    raw_data        JSONB,
    fetch_error     TEXT,
    UNIQUE(property_id, url)
);

CREATE TABLE IF NOT EXISTS changes (
    id              SERIAL PRIMARY KEY,
    property_id     TEXT REFERENCES properties(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    field           TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT
);

CREATE INDEX IF NOT EXISTS idx_changes_property_id ON changes(property_id);
CREATE INDEX IF NOT EXISTS idx_changes_detected_at ON changes(detected_at DESC);

CREATE TABLE IF NOT EXISTS sessions (
    token           TEXT PRIMARY KEY,
    email           TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL
);
```

**Step 3: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    restart: always
    environment:
      POSTGRES_DB: property_tracker
      POSTGRES_USER: tracker
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"

  scraper:
    build: ./scraper
    restart: always
    depends_on:
      - postgres
    env_file: .env
    shm_size: '512mb'

  web:
    build: ./web
    restart: always
    depends_on:
      - postgres
    env_file: .env
    ports:
      - "5713:5713"

volumes:
  pgdata:
```

**Step 4: Create `scraper/pyproject.toml`**

```toml
[project]
name = "property-tracker-scraper"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "asyncpg>=0.30.0",
    "httpx>=0.27.0",
    "gspread>=6.0.0",
    "google-auth>=2.28.0",
    "playwright>=1.49.0",
    "playwright-stealth>=1.0.6",
    "apscheduler>=3.10.4",
    "pydantic-settings>=2.5.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
]
```

**Step 5: Create `scraper/scraper/__init__.py`** (empty)

**Step 6: Create `scraper/scraper/config.py`**

```python
import json
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    google_service_account_json: str = "{}"
    google_sheet_id: str = ""
    google_sheet_range: str = "Sheet1!A:I"
    domain_client_id: str = ""
    domain_client_secret: str = ""
    pushover_app_token: str = ""
    pushover_user_key: str = ""
    scrape_interval_hours: int = 4
    rea_delay_min: int = 5
    rea_delay_max: int = 15

    @property
    def google_credentials(self) -> dict:
        return json.loads(self.google_service_account_json)

    model_config = {"env_file": ".env"}


settings = Settings()
```

**Step 7: Create `scraper/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install uv
COPY pyproject.toml .
RUN uv pip install --system -r pyproject.toml
RUN playwright install chromium --with-deps

COPY scraper/ scraper/
CMD ["python", "-m", "scraper.main"]
```

**Step 8: Verify Postgres starts**

Run: `cp .env.example .env && docker compose up postgres -d`
Expected: Postgres running, tables created from init.sql.

Run: `docker compose exec postgres psql -U tracker -d property_tracker -c '\dt'`
Expected: Lists properties, listing_snapshots, changes, sessions tables.

**Step 9: Commit**

```bash
git add .env.example docker-compose.yml db/ scraper/pyproject.toml scraper/Dockerfile scraper/scraper/__init__.py scraper/scraper/config.py
git commit -m "feat: project scaffolding with docker-compose, postgres schema, python scraper skeleton"
```

---

## Task 2: Python Scraper — Database Layer

**Files:**
- Create: `scraper/scraper/db.py`
- Create: `scraper/scraper/models.py`
- Create: `scraper/tests/__init__.py`
- Create: `scraper/tests/test_models.py`

**Step 1: Create `scraper/scraper/models.py`** — dataclasses shared across scraper

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Property:
    id: str
    address: str
    details: str = ""
    area: str = ""
    advertised_price: str = ""
    sold_price: str = ""
    sold_date: str = ""
    notes: str = ""
    url: str = ""
    url2: str = ""
    sheet_row: int = 0


@dataclass
class ListingSnapshot:
    url: str
    source: str  # 'domain' or 'rea'
    status: str = ""
    price: str = ""
    bedrooms: int | None = None
    bathrooms: int | None = None
    parking: int | None = None
    description: str = ""
    agent_name: str = ""
    agency_name: str = ""
    auction_date: str | None = None
    photo_count: int = 0
    open_home_times: list[str] = field(default_factory=list)
    raw_data: dict | None = None
    fetch_error: str | None = None


@dataclass
class Change:
    field: str
    old_value: str
    new_value: str
```

**Step 2: Create `scraper/scraper/db.py`**

```python
import hashlib
import asyncpg
from datetime import datetime, timezone
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
        agency_name=row["agency_name"] or "", auction_date=str(row["auction_date"]) if row["auction_date"] else None,
        photo_count=row["photo_count"] or 0,
        open_home_times=row["open_home_times"] or [],
        raw_data=row["raw_data"], fetch_error=row["fetch_error"],
    )


async def upsert_snapshot(property_id: str, snapshot: ListingSnapshot):
    import json
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO listing_snapshots (property_id, url, source, status, price,
            bedrooms, bathrooms, parking, description, agent_name, agency_name,
            auction_date, photo_count, open_home_times, raw_data, fetch_error, fetched_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,NOW())
        ON CONFLICT (property_id, url) DO UPDATE SET
            source=EXCLUDED.source, status=EXCLUDED.status, price=EXCLUDED.price,
            bedrooms=EXCLUDED.bedrooms, bathrooms=EXCLUDED.bathrooms,
            parking=EXCLUDED.parking, description=EXCLUDED.description,
            agent_name=EXCLUDED.agent_name, agency_name=EXCLUDED.agency_name,
            auction_date=EXCLUDED.auction_date, photo_count=EXCLUDED.photo_count,
            open_home_times=EXCLUDED.open_home_times, raw_data=EXCLUDED.raw_data,
            fetch_error=EXCLUDED.fetch_error, fetched_at=NOW()
        """,
        property_id, snapshot.url, snapshot.source, snapshot.status, snapshot.price,
        snapshot.bedrooms, snapshot.bathrooms, snapshot.parking, snapshot.description,
        snapshot.agent_name, snapshot.agency_name, snapshot.auction_date,
        snapshot.photo_count, json.dumps(snapshot.open_home_times),
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
```

**Step 3: Create `scraper/tests/__init__.py`** (empty)

**Step 4: Create `scraper/tests/test_models.py`** — verify property_id hashing and model creation

```python
from scraper.db import property_id
from scraper.models import Property, ListingSnapshot, Change


def test_property_id_deterministic():
    assert property_id("12 Smith St, Northcote") == property_id("12 Smith St, Northcote")


def test_property_id_case_insensitive():
    assert property_id("12 Smith St") == property_id("12 smith st")


def test_property_id_strips_whitespace():
    assert property_id("  12 Smith St  ") == property_id("12 Smith St")


def test_listing_snapshot_defaults():
    s = ListingSnapshot(url="http://example.com", source="domain")
    assert s.price == ""
    assert s.bedrooms is None
    assert s.open_home_times == []
    assert s.fetch_error is None


def test_change_creation():
    c = Change(field="price", old_value="$500K", new_value="$520K")
    assert c.field == "price"
```

**Step 5: Run tests**

Run: `cd scraper && uv run pytest tests/ -v`
Expected: All 5 tests pass.

**Step 6: Commit**

```bash
git add scraper/scraper/models.py scraper/scraper/db.py scraper/tests/
git commit -m "feat: database layer with asyncpg and data models"
```

---

## Task 3: Python Scraper — Diff Engine

**Files:**
- Create: `scraper/scraper/diff.py`
- Create: `scraper/tests/test_diff.py`

**Step 1: Write tests for diff engine**

```python
# scraper/tests/test_diff.py
from scraper.diff import diff_snapshots
from scraper.models import ListingSnapshot


def _make_snapshot(**overrides) -> ListingSnapshot:
    defaults = dict(url="http://example.com", source="domain", status="for sale",
                    price="$500K", bedrooms=3, bathrooms=2, parking=1,
                    description="Nice house", agent_name="John", agency_name="Ray White",
                    auction_date=None, photo_count=10)
    defaults.update(overrides)
    return ListingSnapshot(**defaults)


def test_no_changes():
    old = _make_snapshot()
    new = _make_snapshot()
    assert diff_snapshots(old, new) == []


def test_price_change():
    old = _make_snapshot(price="$500K")
    new = _make_snapshot(price="$520K")
    changes = diff_snapshots(old, new)
    assert len(changes) == 1
    assert changes[0].field == "price"
    assert changes[0].old_value == "$500K"
    assert changes[0].new_value == "$520K"


def test_multiple_changes():
    old = _make_snapshot(price="$500K", status="for sale")
    new = _make_snapshot(price="$520K", status="under offer")
    changes = diff_snapshots(old, new)
    assert len(changes) == 2
    fields = {c.field for c in changes}
    assert fields == {"price", "status"}


def test_none_to_value():
    old = _make_snapshot(auction_date=None)
    new = _make_snapshot(auction_date="2026-03-15")
    changes = diff_snapshots(old, new)
    assert len(changes) == 1
    assert changes[0].field == "auction_date"


def test_description_change():
    old = _make_snapshot(description="Nice house")
    new = _make_snapshot(description="Nice house with pool")
    changes = diff_snapshots(old, new)
    assert len(changes) == 1
    assert changes[0].field == "description"


def test_photo_count_change():
    old = _make_snapshot(photo_count=10)
    new = _make_snapshot(photo_count=15)
    changes = diff_snapshots(old, new)
    assert len(changes) == 1
    assert changes[0].field == "photo_count"
```

**Step 2: Run tests to verify they fail**

Run: `cd scraper && uv run pytest tests/test_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.diff'`

**Step 3: Implement diff engine**

```python
# scraper/scraper/diff.py
from .models import ListingSnapshot, Change

TRACKED_FIELDS = [
    "status", "price", "bedrooms", "bathrooms", "parking",
    "description", "agent_name", "agency_name", "auction_date",
    "photo_count",
]


def diff_snapshots(old: ListingSnapshot, new: ListingSnapshot) -> list[Change]:
    changes = []
    for field in TRACKED_FIELDS:
        old_val = str(getattr(old, field) or "")
        new_val = str(getattr(new, field) or "")
        if old_val != new_val:
            changes.append(Change(field=field, old_value=old_val, new_value=new_val))
    return changes
```

**Step 4: Run tests to verify they pass**

Run: `cd scraper && uv run pytest tests/test_diff.py -v`
Expected: All 6 tests pass.

**Step 5: Commit**

```bash
git add scraper/scraper/diff.py scraper/tests/test_diff.py
git commit -m "feat: snapshot diff engine with tracked field comparison"
```

---

## Task 4: Python Scraper — Google Sheets Sync

**Files:**
- Create: `scraper/scraper/sheets.py`

**Step 1: Implement sheets sync**

```python
# scraper/scraper/sheets.py
import logging
import gspread
from google.oauth2.service_account import Credentials
from .config import settings
from .db import property_id, upsert_properties
from .models import Property

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Expected columns: Address, Details, Area, Advertised Price, Sold Price, Sold Date, Notes, URL, URL2
COL_ADDRESS = 0
COL_DETAILS = 1
COL_AREA = 2
COL_ADVERTISED_PRICE = 3
COL_SOLD_PRICE = 4
COL_SOLD_DATE = 5
COL_NOTES = 6
COL_URL = 7
COL_URL2 = 8


def _get_client() -> gspread.Client:
    creds = Credentials.from_service_account_info(
        settings.google_credentials, scopes=SCOPES
    )
    return gspread.authorize(creds)


def _safe_get(row: list[str], index: int) -> str:
    if index < len(row):
        return row[index].strip()
    return ""


def fetch_sheet_rows() -> list[Property]:
    client = _get_client()
    sheet = client.open_by_key(settings.google_sheet_id)
    worksheet = sheet.sheet1
    rows = worksheet.get_all_values()

    if not rows:
        return []

    # Skip header row
    properties = []
    for i, row in enumerate(rows[1:], start=2):
        address = _safe_get(row, COL_ADDRESS)
        if not address:
            continue

        pid = property_id(address)
        properties.append(Property(
            id=pid,
            address=address,
            details=_safe_get(row, COL_DETAILS),
            area=_safe_get(row, COL_AREA),
            advertised_price=_safe_get(row, COL_ADVERTISED_PRICE),
            sold_price=_safe_get(row, COL_SOLD_PRICE),
            sold_date=_safe_get(row, COL_SOLD_DATE),
            notes=_safe_get(row, COL_NOTES),
            url=_safe_get(row, COL_URL),
            url2=_safe_get(row, COL_URL2),
            sheet_row=i,
        ))

    logger.info(f"Fetched {len(properties)} properties from Google Sheet")
    return properties


async def sync_sheet_to_db() -> list[Property]:
    properties = fetch_sheet_rows()
    await upsert_properties(properties)
    return properties
```

**Step 2: Commit**

```bash
git add scraper/scraper/sheets.py
git commit -m "feat: google sheets sync via gspread service account"
```

---

## Task 5: Python Scraper — Domain.com.au API Client

**Files:**
- Create: `scraper/scraper/scrapers/__init__.py`
- Create: `scraper/scraper/scrapers/base.py`
- Create: `scraper/scraper/scrapers/domain_api.py`
- Create: `scraper/tests/test_domain_parser.py`

**Step 1: Create `scraper/scraper/scrapers/__init__.py`** (empty)

**Step 2: Create URL parser tests**

```python
# scraper/tests/test_domain_parser.py
from scraper.scrapers.domain_api import extract_domain_listing_id


def test_extract_full_url():
    url = "https://www.domain.com.au/5401-63-la-trobe-street-melbourne-vic-3000-2018796388"
    assert extract_domain_listing_id(url) == "2018796388"


def test_extract_short_url():
    url = "https://www.domain.com.au/12500140"
    assert extract_domain_listing_id(url) == "12500140"


def test_extract_with_trailing_slash():
    url = "https://www.domain.com.au/5-smith-st-richmond-vic-3121-12345678/"
    assert extract_domain_listing_id(url) == "12345678"
```

**Step 3: Run tests to verify they fail**

Run: `cd scraper && uv run pytest tests/test_domain_parser.py -v`
Expected: FAIL

**Step 4: Implement Domain API client**

```python
# scraper/scraper/scrapers/domain_api.py
import re
import logging
import httpx
from ..config import settings
from ..models import ListingSnapshot

logger = logging.getLogger(__name__)

_cached_token: dict | None = None


def extract_domain_listing_id(url: str) -> str:
    url = url.rstrip("/")
    # Last segment of the URL path, which is always the listing ID
    last_segment = url.split("/")[-1]
    # If the last segment is purely numeric, it's the ID
    # Otherwise, extract trailing numeric portion after last hyphen
    match = re.search(r"(\d+)$", last_segment)
    if match:
        return match.group(1)
    raise ValueError(f"Cannot extract listing ID from URL: {url}")


async def _get_token() -> str:
    global _cached_token
    import time
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
```

**Step 5: Run parser tests**

Run: `cd scraper && uv run pytest tests/test_domain_parser.py -v`
Expected: All 3 tests pass.

**Step 6: Commit**

```bash
git add scraper/scraper/scrapers/ scraper/tests/test_domain_parser.py
git commit -m "feat: domain.com.au API client with OAuth token caching"
```

---

## Task 6: Python Scraper — realestate.com.au Playwright Scraper

**Files:**
- Create: `scraper/scraper/scrapers/rea.py`
- Create: `scraper/tests/test_rea_parser.py`

**Step 1: Write parser tests with sample HTML**

```python
# scraper/tests/test_rea_parser.py
import json
from scraper.scrapers.rea import parse_rea_page_data

# Simplified mock of the ArgonautExchange structure
MOCK_LISTING_DATA = {
    "status": "Buy",
    "price": {"display": "$800,000 - $880,000"},
    "generalFeatures": {
        "bedrooms": {"value": 3},
        "bathrooms": {"value": 2},
        "parkingSpaces": {"value": 2},
    },
    "description": "A beautiful family home with a spacious backyard.",
    "listers": [{"name": "Jane Smith"}],
    "listingCompany": {"name": "McGrath"},
    "auctionDetails": None,
    "media": {"images": [{"uri": "img1.jpg"}, {"uri": "img2.jpg"}, {"uri": "img3.jpg"}]},
}


def test_parse_basic_fields():
    snapshot = parse_rea_page_data(MOCK_LISTING_DATA, "https://www.realestate.com.au/property-house-vic-test-123")
    assert snapshot.source == "rea"
    assert snapshot.price == "$800,000 - $880,000"
    assert snapshot.bedrooms == 3
    assert snapshot.bathrooms == 2
    assert snapshot.parking == 2
    assert snapshot.agent_name == "Jane Smith"
    assert snapshot.agency_name == "McGrath"
    assert snapshot.photo_count == 3


def test_parse_missing_fields():
    data = {"status": "Sold"}
    snapshot = parse_rea_page_data(data, "https://example.com")
    assert snapshot.status == "Sold"
    assert snapshot.bedrooms is None
    assert snapshot.price == ""
    assert snapshot.photo_count == 0


def test_parse_description_truncated():
    data = {"description": "x" * 1000}
    snapshot = parse_rea_page_data(data, "https://example.com")
    assert len(snapshot.description) == 500
```

**Step 2: Run tests to verify they fail**

Run: `cd scraper && uv run pytest tests/test_rea_parser.py -v`
Expected: FAIL

**Step 3: Implement REA scraper**

```python
# scraper/scraper/scrapers/rea.py
import json
import re
import logging
from playwright.async_api import async_playwright
from ..models import ListingSnapshot

logger = logging.getLogger(__name__)


def parse_rea_page_data(data: dict, url: str) -> ListingSnapshot:
    """Parse listing data extracted from REA page into a ListingSnapshot."""
    general = data.get("generalFeatures", {})
    price_info = data.get("price", {})
    listers = data.get("listers", [])
    company = data.get("listingCompany", {})
    auction = data.get("auctionDetails")
    media = data.get("media", {})
    images = media.get("images", []) if isinstance(media, dict) else []

    return ListingSnapshot(
        url=url,
        source="rea",
        status=data.get("status", ""),
        price=price_info.get("display", "") if isinstance(price_info, dict) else "",
        bedrooms=general.get("bedrooms", {}).get("value") if isinstance(general.get("bedrooms"), dict) else None,
        bathrooms=general.get("bathrooms", {}).get("value") if isinstance(general.get("bathrooms"), dict) else None,
        parking=general.get("parkingSpaces", {}).get("value") if isinstance(general.get("parkingSpaces"), dict) else None,
        description=(data.get("description", "") or "")[:500],
        agent_name=listers[0].get("name", "") if listers else "",
        agency_name=company.get("name", "") if isinstance(company, dict) else "",
        auction_date=auction.get("dateTime") if isinstance(auction, dict) else None,
        photo_count=len(images),
        open_home_times=[],
        raw_data=data,
    )


def _extract_listing_data(html: str) -> dict | None:
    """Try to extract listing data from REA page HTML.

    REA embeds data in window.ArgonautExchange as nested JSON.
    Falls back to __NEXT_DATA__ if available.
    """
    # Try ArgonautExchange
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

    # Try __NEXT_DATA__
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


async def scrape_rea(url: str, browser=None) -> ListingSnapshot:
    """Scrape a realestate.com.au listing page using Playwright."""
    should_close = browser is None

    try:
        if browser is None:
            pw = await async_playwright().__aenter__()
            browser = await pw.chromium.launch(headless=True)

        context = await browser.new_context(
            locale="en-AU",
            timezone_id="Australia/Sydney",
        )
        page = await context.new_page()

        try:
            # Import stealth if available
            from playwright_stealth import stealth_async
            await stealth_async(page)
        except ImportError:
            logger.warning("playwright-stealth not installed, proceeding without stealth")

        response = await page.goto(url, wait_until="networkidle", timeout=30000)
        if response and response.status >= 400:
            await context.close()
            return ListingSnapshot(
                url=url, source="rea",
                fetch_error=f"HTTP {response.status}",
            )

        html = await page.content()
        await context.close()

        data = _extract_listing_data(html)
        if data is None:
            return ListingSnapshot(
                url=url, source="rea",
                fetch_error="Could not extract listing data from page",
            )

        return parse_rea_page_data(data, url)

    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        return ListingSnapshot(url=url, source="rea", fetch_error=str(e))

    finally:
        if should_close and browser:
            await browser.close()
```

**Step 4: Run parser tests**

Run: `cd scraper && uv run pytest tests/test_rea_parser.py -v`
Expected: All 3 tests pass.

**Step 5: Commit**

```bash
git add scraper/scraper/scrapers/rea.py scraper/tests/test_rea_parser.py
git commit -m "feat: realestate.com.au playwright scraper with ArgonautExchange parser"
```

---

## Task 7: Python Scraper — Pushover Notifications

**Files:**
- Create: `scraper/scraper/notify.py`

**Step 1: Implement Pushover client**

```python
# scraper/scraper/notify.py
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
        f"{c.field}: {c.old_value} → {c.new_value}" for c in changes
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
```

**Step 2: Commit**

```bash
git add scraper/scraper/notify.py
git commit -m "feat: pushover notification client"
```

---

## Task 8: Python Scraper — Main Loop + Scheduler

**Files:**
- Create: `scraper/scraper/main.py`

**Step 1: Implement main entry point with APScheduler**

```python
# scraper/scraper/main.py
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

    # Reuse one browser for all REA scrapes
    rea_browser = None
    try:
        from playwright.async_api import async_playwright
        pw = await async_playwright().__aenter__()
        rea_browser = await pw.chromium.launch(headless=True)
    except Exception as e:
        logger.warning(f"Failed to launch browser for REA scraping: {e}")

    for prop in properties:
        for url in [prop.url, prop.url2]:
            if not url:
                continue

            try:
                if "domain.com.au" in url:
                    snapshot = await scrape_domain(url)
                elif "realestate.com.au" in url:
                    snapshot = await scrape_rea(url, browser=rea_browser)
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

            # Random delay between requests
            delay = random.uniform(settings.rea_delay_min, settings.rea_delay_max)
            await asyncio.sleep(delay)

    if rea_browser:
        await rea_browser.close()

    logger.info(
        f"Scrape cycle complete: {len(properties)} properties, "
        f"{total_changes} changes detected, {errors} errors"
    )


def main():
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

    # Run once immediately on startup
    loop = asyncio.new_event_loop()
    loop.run_until_complete(scrape_all())

    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        scheduler.shutdown()
        loop.run_until_complete(db.close_pool())


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add scraper/scraper/main.py
git commit -m "feat: scraper main loop with APScheduler, runs every 4 hours"
```

---

## Task 9: SvelteKit Frontend — Project Scaffold

**Files:**
- Create: `web/` (via `npx sv create`)
- Modify: `web/svelte.config.js`
- Create: `web/Dockerfile`

**Step 1: Scaffold SvelteKit project**

Run:
```bash
cd /path/to/gsheet-property-tracker
npx sv create web --template minimal --types ts
cd web
npm install
npm install -D @sveltejs/adapter-node
npm install postgres
npm install -D tailwindcss @tailwindcss/vite
```

**Step 2: Configure adapter-node in `web/svelte.config.js`**

```javascript
import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/kit/vite';

export default {
    preprocess: vitePreprocess(),
    kit: {
        adapter: adapter({ out: 'build' }),
    },
};
```

**Step 3: Configure Tailwind in `web/vite.config.ts`**

```typescript
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
    plugins: [tailwindcss(), sveltekit()],
});
```

**Step 4: Add Tailwind to `web/src/app.css`**

```css
@import 'tailwindcss';
```

**Step 5: Create `web/Dockerfile`**

```dockerfile
FROM node:22-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
ENV PORT=5713
EXPOSE 5713
CMD ["node", "build/index.js"]
```

**Step 6: Verify it builds**

Run: `cd web && npm run build`
Expected: Build succeeds, output in `web/build/`.

**Step 7: Commit**

```bash
git add web/
git commit -m "feat: sveltekit project scaffold with adapter-node and tailwind"
```

---

## Task 10: SvelteKit Frontend — Database Client + Types

**Files:**
- Create: `web/src/lib/server/db.ts`
- Create: `web/src/lib/types.ts`
- Modify: `web/src/app.d.ts`

**Step 1: Create `web/src/lib/types.ts`**

```typescript
export interface Property {
    id: string;
    address: string;
    details: string;
    area: string;
    advertised_price: string;
    sold_price: string;
    sold_date: string;
    notes: string;
    url: string;
    url2: string;
    last_checked: string | null;
    has_recent_changes: boolean;
    last_change_at: string | null;
}

export interface Change {
    id: number;
    property_id: string;
    url: string;
    detected_at: string;
    field: string;
    old_value: string;
    new_value: string;
}

export interface ListingSnapshot {
    id: number;
    property_id: string;
    url: string;
    source: string;
    fetched_at: string;
    status: string;
    price: string;
    bedrooms: number | null;
    bathrooms: number | null;
    parking: number | null;
    description: string;
    agent_name: string;
    agency_name: string;
    auction_date: string | null;
    photo_count: number;
    fetch_error: string | null;
}
```

**Step 2: Create `web/src/lib/server/db.ts`**

```typescript
import postgres from 'postgres';
import { env } from '$env/dynamic/private';

const sql = postgres(env.DATABASE_URL);

export default sql;
```

**Step 3: Update `web/src/app.d.ts`**

```typescript
declare global {
    namespace App {
        interface Locals {
            user: string | null;
        }
    }
}

export {};
```

**Step 4: Commit**

```bash
git add web/src/lib/ web/src/app.d.ts
git commit -m "feat: postgres client, shared types, app type declarations"
```

---

## Task 11: SvelteKit Frontend — Authentication

**Files:**
- Create: `web/src/lib/server/auth.ts`
- Modify: `web/src/hooks.server.ts`
- Create: `web/src/routes/login/+page.svelte`
- Create: `web/src/routes/login/+page.server.ts`
- Create: `web/src/routes/api/logout/+server.ts`

**Step 1: Create `web/src/lib/server/auth.ts`**

```typescript
import { env } from '$env/dynamic/private';
import sql from './db';
import crypto from 'node:crypto';

export async function validateCredentials(email: string, password: string): Promise<boolean> {
    return email === env.AUTH_EMAIL && password === env.AUTH_PASSWORD;
}

export async function createSession(email: string): Promise<string> {
    const token = crypto.randomBytes(32).toString('hex');
    const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000); // 7 days
    await sql`
        INSERT INTO sessions (token, email, expires_at)
        VALUES (${token}, ${email}, ${expiresAt})
    `;
    return token;
}

export async function getSession(token: string): Promise<string | null> {
    const [session] = await sql`
        SELECT email FROM sessions
        WHERE token = ${token} AND expires_at > NOW()
    `;
    return session?.email ?? null;
}

export async function deleteSession(token: string): Promise<void> {
    await sql`DELETE FROM sessions WHERE token = ${token}`;
}
```

**Step 2: Create `web/src/hooks.server.ts`**

```typescript
import type { Handle } from '@sveltejs/kit';
import { getSession } from '$lib/server/auth';

export const handle: Handle = async ({ event, resolve }) => {
    const sessionToken = event.cookies.get('session');
    if (sessionToken) {
        event.locals.user = await getSession(sessionToken);
    } else {
        event.locals.user = null;
    }
    return resolve(event);
};
```

**Step 3: Create `web/src/routes/login/+page.server.ts`**

```typescript
import { fail, redirect } from '@sveltejs/kit';
import type { Actions } from './$types';
import { validateCredentials, createSession } from '$lib/server/auth';

export const actions: Actions = {
    default: async ({ request, cookies }) => {
        const data = await request.formData();
        const email = data.get('email') as string;
        const password = data.get('password') as string;

        if (!email || !password) {
            return fail(400, { error: 'Email and password required', email });
        }

        const valid = await validateCredentials(email, password);
        if (!valid) {
            return fail(401, { error: 'Invalid credentials', email });
        }

        const token = await createSession(email);
        cookies.set('session', token, {
            path: '/',
            httpOnly: true,
            sameSite: 'lax',
            secure: true,
            maxAge: 7 * 24 * 60 * 60, // 7 days
        });

        redirect(302, '/');
    },
};
```

**Step 4: Create `web/src/routes/login/+page.svelte`**

```svelte
<script lang="ts">
    import type { ActionData } from './$types';
    let { form }: { form: ActionData } = $props();
</script>

<div class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="w-full max-w-sm">
        <h1 class="text-2xl font-bold text-center mb-8">Property Tracker</h1>

        {#if form?.error}
            <div class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
                {form.error}
            </div>
        {/if}

        <form method="POST" class="bg-white shadow rounded-lg p-6 space-y-4">
            <div>
                <label for="email" class="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input
                    type="email" name="email" id="email" required
                    value={form?.email ?? ''}
                    class="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </div>
            <div>
                <label for="password" class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input
                    type="password" name="password" id="password" required
                    class="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </div>
            <button
                type="submit"
                class="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition-colors"
            >
                Sign in
            </button>
        </form>
    </div>
</div>
```

**Step 5: Create `web/src/routes/api/logout/+server.ts`**

```typescript
import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { deleteSession } from '$lib/server/auth';

export const POST: RequestHandler = async ({ cookies }) => {
    const token = cookies.get('session');
    if (token) {
        await deleteSession(token);
        cookies.delete('session', { path: '/' });
    }
    redirect(302, '/login');
};
```

**Step 6: Commit**

```bash
git add web/src/lib/server/auth.ts web/src/hooks.server.ts web/src/routes/login/ web/src/routes/api/logout/
git commit -m "feat: cookie-based auth with login page and session management"
```

---

## Task 12: SvelteKit Frontend — Dashboard Page

**Files:**
- Create: `web/src/routes/(app)/+layout.server.ts`
- Create: `web/src/routes/(app)/+page.server.ts`
- Create: `web/src/routes/(app)/+page.svelte`
- Create: `web/src/routes/+layout.svelte`

**Step 1: Create root layout (`web/src/routes/+layout.svelte`)**

```svelte
<script lang="ts">
    import '../app.css';
    let { children } = $props();
</script>

{@render children()}
```

**Step 2: Create auth guard (`web/src/routes/(app)/+layout.server.ts`)**

```typescript
import { redirect } from '@sveltejs/kit';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ locals }) => {
    if (!locals.user) {
        redirect(302, '/login');
    }
    return { user: locals.user };
};
```

**Step 3: Create dashboard data loader (`web/src/routes/(app)/+page.server.ts`)**

```typescript
import type { PageServerLoad } from './$types';
import sql from '$lib/server/db';

export const load: PageServerLoad = async () => {
    const properties = await sql`
        SELECT p.*,
            EXISTS(
                SELECT 1 FROM changes c
                WHERE c.property_id = p.id
                AND c.detected_at > NOW() - INTERVAL '48 hours'
            ) as has_recent_changes,
            (SELECT MAX(c.detected_at) FROM changes c WHERE c.property_id = p.id)
                as last_change_at
        FROM properties p
        ORDER BY p.updated_at DESC
    `;

    const areas = await sql`
        SELECT DISTINCT area FROM properties WHERE area IS NOT NULL AND area != '' ORDER BY area
    `;

    return {
        properties: properties.map(p => ({
            ...p,
            last_checked: p.last_checked?.toISOString() ?? null,
            last_change_at: p.last_change_at?.toISOString() ?? null,
            created_at: undefined,
            updated_at: undefined,
        })),
        areas: areas.map(a => a.area),
    };
};
```

**Step 4: Create dashboard page (`web/src/routes/(app)/+page.svelte`)**

```svelte
<script lang="ts">
    import type { PageData } from './$types';
    import type { Property } from '$lib/types';

    let { data }: { data: PageData } = $props();

    let search = $state('');
    let areaFilter = $state('all');
    let bedsFilter = $state('any');
    let statusFilter = $state('all');
    let view = $state<'cards' | 'table'>('cards');

    let filtered = $derived(
        (data.properties as Property[]).filter((p) => {
            if (search && !p.address.toLowerCase().includes(search.toLowerCase()) &&
                !p.area?.toLowerCase().includes(search.toLowerCase())) {
                return false;
            }
            if (areaFilter !== 'all' && p.area !== areaFilter) return false;
            if (bedsFilter !== 'any') {
                const beds = parseInt(p.details?.match(/(\d+)\s*Bed/i)?.[1] ?? '0');
                if (beds !== parseInt(bedsFilter)) return false;
            }
            if (statusFilter === 'sold' && !p.sold_price) return false;
            if (statusFilter === 'active' && p.sold_price) return false;
            return true;
        })
    );

    function timeAgo(dateStr: string | null): string {
        if (!dateStr) return 'never';
        const diff = Date.now() - new Date(dateStr).getTime();
        const hours = Math.floor(diff / 3600000);
        if (hours < 1) return 'just now';
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        return `${days}d ago`;
    }
</script>

<div class="min-h-screen bg-gray-50">
    <header class="bg-white shadow-sm border-b">
        <div class="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
            <h1 class="text-xl font-bold">Property Tracker</h1>
            <form method="POST" action="/api/logout">
                <button class="text-sm text-gray-500 hover:text-gray-700">Logout</button>
            </form>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 py-6">
        <!-- Search + Filters -->
        <div class="bg-white rounded-lg shadow-sm border p-4 mb-6 space-y-3">
            <input
                type="text" placeholder="Search by address or area..."
                bind:value={search}
                class="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <div class="flex flex-wrap gap-3 items-center">
                <select bind:value={areaFilter} class="border border-gray-300 rounded px-2 py-1 text-sm">
                    <option value="all">All Areas</option>
                    {#each data.areas as area}
                        <option value={area}>{area}</option>
                    {/each}
                </select>
                <select bind:value={bedsFilter} class="border border-gray-300 rounded px-2 py-1 text-sm">
                    <option value="any">Any Beds</option>
                    {#each [1,2,3,4,5] as n}
                        <option value={String(n)}>{n} Bed</option>
                    {/each}
                </select>
                <select bind:value={statusFilter} class="border border-gray-300 rounded px-2 py-1 text-sm">
                    <option value="all">All Status</option>
                    <option value="active">Active</option>
                    <option value="sold">Sold</option>
                </select>
                <div class="ml-auto flex gap-1">
                    <button
                        onclick={() => view = 'cards'}
                        class="px-3 py-1 text-sm rounded {view === 'cards' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'}"
                    >Cards</button>
                    <button
                        onclick={() => view = 'table'}
                        class="px-3 py-1 text-sm rounded {view === 'table' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'}"
                    >Table</button>
                </div>
                <span class="text-sm text-gray-500">{filtered.length} properties</span>
            </div>
        </div>

        <!-- Card View -->
        {#if view === 'cards'}
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {#each filtered as prop (prop.id)}
                    <a
                        href="/property/{prop.id}"
                        class="bg-white rounded-lg shadow-sm border p-4 hover:shadow-md transition-shadow
                            {prop.has_recent_changes ? 'border-l-4 border-l-amber-400' : ''}"
                    >
                        <h3 class="font-semibold text-sm leading-tight mb-2">{prop.address}</h3>
                        <div class="text-xs text-gray-500 space-y-1">
                            {#if prop.details}<p>{prop.details}</p>{/if}
                            {#if prop.area}<p>{prop.area}</p>{/if}
                            {#if prop.advertised_price}
                                <p class="text-sm font-medium text-gray-900">{prop.advertised_price}</p>
                            {/if}
                            {#if prop.sold_price}
                                <p class="text-green-700 font-medium">Sold: {prop.sold_price}</p>
                            {/if}
                            {#if prop.has_recent_changes}
                                <p class="text-amber-600 text-xs">Updated {timeAgo(prop.last_change_at)}</p>
                            {/if}
                        </div>
                    </a>
                {/each}
            </div>
        {/if}

        <!-- Table View -->
        {#if view === 'table'}
            <div class="bg-white rounded-lg shadow-sm border overflow-x-auto">
                <table class="w-full text-sm">
                    <thead class="bg-gray-50 border-b">
                        <tr>
                            <th class="text-left px-4 py-2 font-medium">Address</th>
                            <th class="text-left px-4 py-2 font-medium">Details</th>
                            <th class="text-left px-4 py-2 font-medium">Area</th>
                            <th class="text-left px-4 py-2 font-medium">Price</th>
                            <th class="text-left px-4 py-2 font-medium">Sold</th>
                            <th class="text-left px-4 py-2 font-medium">Checked</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each filtered as prop (prop.id)}
                            <tr class="border-b hover:bg-gray-50 {prop.has_recent_changes ? 'bg-amber-50' : ''}">
                                <td class="px-4 py-2">
                                    <a href="/property/{prop.id}" class="text-blue-600 hover:underline">{prop.address}</a>
                                </td>
                                <td class="px-4 py-2 text-gray-600">{prop.details || '-'}</td>
                                <td class="px-4 py-2 text-gray-600">{prop.area || '-'}</td>
                                <td class="px-4 py-2">{prop.advertised_price || '-'}</td>
                                <td class="px-4 py-2 text-green-700">{prop.sold_price || '-'}</td>
                                <td class="px-4 py-2 text-gray-400 text-xs">{timeAgo(prop.last_checked)}</td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {/if}
    </main>
</div>
```

**Step 5: Verify build**

Run: `cd web && npm run build`
Expected: Build succeeds.

**Step 6: Commit**

```bash
git add web/src/routes/
git commit -m "feat: dashboard page with card/table toggle, search, and filters"
```

---

## Task 13: SvelteKit Frontend — Property Detail Page

**Files:**
- Create: `web/src/routes/(app)/property/[id]/+page.server.ts`
- Create: `web/src/routes/(app)/property/[id]/+page.svelte`

**Step 1: Create data loader (`web/src/routes/(app)/property/[id]/+page.server.ts`)**

```typescript
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import sql from '$lib/server/db';

export const load: PageServerLoad = async ({ params }) => {
    const [property] = await sql`
        SELECT * FROM properties WHERE id = ${params.id}
    `;

    if (!property) {
        error(404, 'Property not found');
    }

    const changes = await sql`
        SELECT * FROM changes
        WHERE property_id = ${params.id}
        ORDER BY detected_at DESC
        LIMIT 100
    `;

    const snapshots = await sql`
        SELECT * FROM listing_snapshots
        WHERE property_id = ${params.id}
    `;

    return {
        property: {
            ...property,
            last_checked: property.last_checked?.toISOString() ?? null,
        },
        changes: changes.map(c => ({
            ...c,
            detected_at: c.detected_at.toISOString(),
        })),
        snapshots: snapshots.map(s => ({
            ...s,
            fetched_at: s.fetched_at.toISOString(),
            auction_date: s.auction_date?.toISOString() ?? null,
        })),
    };
};
```

**Step 2: Create property detail page (`web/src/routes/(app)/property/[id]/+page.svelte`)**

```svelte
<script lang="ts">
    import type { PageData } from './$types';

    let { data }: { data: PageData } = $props();
    const { property, changes, snapshots } = data;

    function formatDate(dateStr: string): string {
        return new Date(dateStr).toLocaleDateString('en-AU', {
            day: 'numeric', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    }

    function urlDomain(url: string): string {
        try {
            return new URL(url).hostname.replace('www.', '');
        } catch {
            return url;
        }
    }
</script>

<div class="min-h-screen bg-gray-50">
    <header class="bg-white shadow-sm border-b">
        <div class="max-w-4xl mx-auto px-4 py-4">
            <a href="/" class="text-sm text-blue-600 hover:underline mb-2 inline-block">&larr; Back</a>
            <h1 class="text-xl font-bold">{property.address}</h1>
        </div>
    </header>

    <main class="max-w-4xl mx-auto px-4 py-6 space-y-6">
        <!-- Property Details -->
        <div class="bg-white rounded-lg shadow-sm border p-6">
            <div class="grid grid-cols-2 gap-4 text-sm">
                {#if property.details}
                    <div>
                        <span class="text-gray-500">Details</span>
                        <p class="font-medium">{property.details}</p>
                    </div>
                {/if}
                {#if property.area}
                    <div>
                        <span class="text-gray-500">Area</span>
                        <p class="font-medium">{property.area}</p>
                    </div>
                {/if}
                {#if property.advertised_price}
                    <div>
                        <span class="text-gray-500">Advertised Price</span>
                        <p class="font-medium">{property.advertised_price}</p>
                    </div>
                {/if}
                {#if property.sold_price}
                    <div>
                        <span class="text-gray-500">Sold Price</span>
                        <p class="font-medium text-green-700">{property.sold_price}</p>
                    </div>
                {/if}
                {#if property.sold_date}
                    <div>
                        <span class="text-gray-500">Sold Date</span>
                        <p class="font-medium">{property.sold_date}</p>
                    </div>
                {/if}
            </div>

            {#if property.notes}
                <div class="mt-4 pt-4 border-t">
                    <span class="text-sm text-gray-500">Notes</span>
                    <p class="text-sm mt-1">{property.notes}</p>
                </div>
            {/if}

            <!-- Listing Links -->
            <div class="mt-4 pt-4 border-t flex gap-3">
                {#if property.url}
                    <a href={property.url} target="_blank" rel="noopener"
                       class="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
                        {urlDomain(property.url)} &nearr;
                    </a>
                {/if}
                {#if property.url2}
                    <a href={property.url2} target="_blank" rel="noopener"
                       class="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
                        {urlDomain(property.url2)} &nearr;
                    </a>
                {/if}
            </div>

            {#if property.last_checked}
                <p class="text-xs text-gray-400 mt-3">Last checked: {formatDate(property.last_checked)}</p>
            {/if}
        </div>

        <!-- Current Snapshots -->
        {#if snapshots.length > 0}
            <div class="bg-white rounded-lg shadow-sm border p-6">
                <h2 class="font-semibold mb-4">Current Listing Data</h2>
                <div class="space-y-4">
                    {#each snapshots as snap}
                        <div class="border rounded p-4 text-sm">
                            <div class="flex items-center justify-between mb-2">
                                <span class="font-medium">{urlDomain(snap.url)}</span>
                                {#if snap.fetch_error}
                                    <span class="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">Error</span>
                                {:else}
                                    <span class="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">{snap.status || 'OK'}</span>
                                {/if}
                            </div>
                            {#if snap.fetch_error}
                                <p class="text-red-600 text-xs">{snap.fetch_error}</p>
                            {:else}
                                <div class="grid grid-cols-2 gap-2 text-xs text-gray-600">
                                    {#if snap.price}<p>Price: {snap.price}</p>{/if}
                                    {#if snap.bedrooms != null}<p>Beds: {snap.bedrooms} / Bath: {snap.bathrooms} / Car: {snap.parking}</p>{/if}
                                    {#if snap.agent_name}<p>Agent: {snap.agent_name} ({snap.agency_name})</p>{/if}
                                    {#if snap.auction_date}<p>Auction: {formatDate(snap.auction_date)}</p>{/if}
                                    {#if snap.photo_count}<p>Photos: {snap.photo_count}</p>{/if}
                                </div>
                            {/if}
                            <p class="text-xs text-gray-400 mt-2">Fetched: {formatDate(snap.fetched_at)}</p>
                        </div>
                    {/each}
                </div>
            </div>
        {/if}

        <!-- Change History -->
        <div class="bg-white rounded-lg shadow-sm border p-6">
            <h2 class="font-semibold mb-4">Change History</h2>
            {#if changes.length === 0}
                <p class="text-sm text-gray-500">No changes detected yet.</p>
            {:else}
                <div class="space-y-3">
                    {#each changes as change}
                        <div class="border-l-2 border-gray-200 pl-4 py-1">
                            <p class="text-xs text-gray-400">{formatDate(change.detected_at)}</p>
                            <p class="text-sm">
                                <span class="font-medium">{change.field}</span>:
                                <span class="text-red-600 line-through">{change.old_value || '(empty)'}</span>
                                &rarr;
                                <span class="text-green-700">{change.new_value || '(empty)'}</span>
                            </p>
                            <p class="text-xs text-gray-400">{urlDomain(change.url)}</p>
                        </div>
                    {/each}
                </div>
            {/if}
        </div>
    </main>
</div>
```

**Step 3: Verify build**

Run: `cd web && npm run build`
Expected: Build succeeds.

**Step 4: Commit**

```bash
git add web/src/routes/\(app\)/property/
git commit -m "feat: property detail page with snapshot display and change history"
```

---

## Task 14: Deployment Configs

**Files:**
- Create: `deploy/scraper.service`
- Create: `deploy/web.service`
- Create: `.gitignore`

**Step 1: Create systemd service files**

```ini
# deploy/scraper.service
[Unit]
Description=Property Tracker Scraper
After=postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/gsheet-property-tracker/scraper
ExecStart=/home/pi/.local/bin/uv run python -m scraper.main
Restart=always
RestartSec=30
EnvironmentFile=/home/pi/gsheet-property-tracker/.env

[Install]
WantedBy=multi-user.target
```

```ini
# deploy/web.service
[Unit]
Description=Property Tracker Web UI
After=postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/gsheet-property-tracker/web
ExecStart=/usr/bin/node build/index.js
Restart=always
RestartSec=10
EnvironmentFile=/home/pi/gsheet-property-tracker/.env
Environment=PORT=5713

[Install]
WantedBy=multi-user.target
```

**Step 2: Create `.gitignore`**

```
# Python
__pycache__/
*.pyc
.venv/

# Node
node_modules/
web/build/
web/.svelte-kit/

# Environment
.env

# Docker
pgdata/

# OS
.DS_Store

# Playwright
playwright-report/

# Wrangler (legacy)
.wrangler/
```

**Step 3: Commit**

```bash
git add deploy/ .gitignore
git commit -m "feat: systemd service files and gitignore"
```

---

## Task 15: End-to-End Smoke Test

**Step 1: Start Postgres**

Run: `cp .env.example .env && docker compose up postgres -d`
Expected: Postgres running with schema initialized.

**Step 2: Run Python tests**

Run: `cd scraper && uv sync && uv run pytest tests/ -v`
Expected: All tests pass (models, diff, domain parser, rea parser).

**Step 3: Build and start the web app**

Run: `cd web && npm install && npm run build`
Expected: Build succeeds.

**Step 4: Verify web app starts**

Run: `cd web && DATABASE_URL=postgresql://tracker:changeme@localhost:5432/property_tracker AUTH_EMAIL=test@test.com AUTH_PASSWORD=test node build/index.js &`
Expected: Server starts on port 5713.

Run: `curl -s http://localhost:5713/login | head -20`
Expected: HTML containing "Property Tracker" and login form.

**Step 5: Stop test server, commit if any fixes were needed**

```bash
kill %1  # stop background node process
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Scaffolding + Docker + DB schema | `.env.example`, `docker-compose.yml`, `db/init.sql`, `scraper/` skeleton |
| 2 | Database layer | `scraper/scraper/db.py`, `models.py`, tests |
| 3 | Diff engine | `scraper/scraper/diff.py`, tests |
| 4 | Google Sheets sync | `scraper/scraper/sheets.py` |
| 5 | Domain.com.au API client | `scraper/scraper/scrapers/domain_api.py`, tests |
| 6 | REA Playwright scraper | `scraper/scraper/scrapers/rea.py`, tests |
| 7 | Pushover notifications | `scraper/scraper/notify.py` |
| 8 | Main loop + scheduler | `scraper/scraper/main.py` |
| 9 | SvelteKit scaffold | `web/` project setup |
| 10 | DB client + types | `web/src/lib/` |
| 11 | Authentication | Login page, hooks, session management |
| 12 | Dashboard page | Card/table view with search and filters |
| 13 | Property detail page | Snapshots + change history |
| 14 | Deployment configs | systemd units, `.gitignore` |
| 15 | Smoke test | End-to-end verification |
