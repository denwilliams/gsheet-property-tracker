# Property Tracker - Architecture Design

## System Overview

```
┌───────────────────────────────────────────────────────────┐
│                    Raspberry Pi 4                          │
│                                                           │
│  ┌─────────────────────┐    ┌──────────────────────────┐  │
│  │  Python Scraper      │    │  SvelteKit App            │  │
│  │  (systemd service)   │    │  (Node adapter, port 5713)│  │
│  │                      │    │                           │  │
│  │  - APScheduler       │    │  /login                   │  │
│  │    (every 4 hours)   │    │  / (dashboard)            │  │
│  │  - Google Sheets API │    │  /property/[id]           │  │
│  │  - Playwright        │    │  /api/properties          │  │
│  │    (REA scraping)    │    │                           │  │
│  │  - Domain.com.au API │    │  Reads from Postgres      │  │
│  │  - Diff engine       │    │  Client-side search/filter│  │
│  │  - Pushover alerts   │    │                           │  │
│  └──────────┬───────────┘    └────────────┬──────────────┘  │
│             │                             │                 │
│  ┌──────────▼─────────────────────────────▼──────────────┐  │
│  │                    PostgreSQL                          │  │
│  │                                                        │  │
│  │  properties        → synced from Google Sheet          │  │
│  │  listing_snapshots → latest scraped data per URL       │  │
│  │  changes           → detected changes log              │  │
│  │  sessions          → auth sessions                     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  cloudflared (Cloudflare Tunnel)                       │  │
│  │  → maps tracker.yourdomain.com to localhost:5713       │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   Google Sheets API    Domain.com.au API    realestate.com.au
   (Service Account)    (Official, free)     (Playwright + stealth)
```

---

## Key Architecture Decisions

### 1. Two Processes, One Machine

- **Python scraper service** (systemd): Background daemon that runs on a schedule. Reads Google Sheet, scrapes listings, diffs snapshots, writes to Postgres, sends Pushover notifications.
- **SvelteKit web app** (systemd): Serves the UI, reads from Postgres. No scraping logic — purely a read-only dashboard.

Clean separation: the scraper can crash/restart without affecting the UI, and vice versa.

### 2. Raspberry Pi Advantages for Scraping

| Factor | Why Pi wins |
|--------|------------|
| Residential IP | Australian ISP IP, not flagged as datacenter |
| Full browser | Playwright + Chromium runs natively |
| Persistent state | Real filesystem, Postgres, no cold starts |
| No CPU time limits | Can spend 30+ seconds per page if needed |
| Cost | $0/month (hardware you own, power is negligible) |

### 3. Listing Data Fetching Strategy

| Source | Method | Reliability |
|--------|--------|-------------|
| **domain.com.au** | Playwright + parse `__NEXT_DATA__` JSON | High — Next.js site, lighter bot protection than REA |
| **realestate.com.au** | Playwright + stealth plugin + parse `ArgonautExchange` | Medium-High — residential IP + real browser bypasses most Kasada checks |

**Domain.com.au**: Playwright scraping. Domain is a Next.js app that embeds listing data in a `<script id="__NEXT_DATA__">` tag. Lighter bot protection than REA — no Kasada. The official API's listings endpoint requires a paid plan, so we scrape instead.

**realestate.com.au**: Playwright with `playwright-stealth` on a residential IP. The Pi's Australian residential IP is a huge advantage — Kasada primarily blocks datacenter IPs. Random 5-15s delays between requests. Parse the `ArgonautExchange` JSON from page source.

Both scrapers share a single Chromium browser instance per scrape cycle to minimize memory usage.

### 4. PostgreSQL over KV/SQLite

Postgres gives us:
- Proper relational schema (properties → snapshots → changes)
- Rich querying for the frontend (joins, aggregations, date ranges)
- JSONB for flexible snapshot storage
- Robust concurrent access (scraper writing while UI reads)
- Runs fine on Pi 4 with 4GB+ RAM

### 5. Google Sheets: gspread (Python)

On a Pi, we can use the standard `gspread` library with full Google auth. No need for the bare-metal JWT approach we needed for Cloudflare Workers.

### 6. External Access via Cloudflare Tunnel

`cloudflared` runs as a systemd service on the Pi, creates a secure tunnel to Cloudflare's edge. Maps a subdomain (e.g., `tracker.yourdomain.com`) to `localhost:5713`. No port forwarding, no dynamic DNS, free.

---

## Project Structure

```
gsheet-property-tracker/
├── scraper/                         # Python scraper service
│   ├── pyproject.toml               # Dependencies (uv/pip)
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── main.py                  # Entry point, scheduler setup
│   │   ├── config.py                # Environment config (pydantic-settings)
│   │   ├── db.py                    # Postgres connection + queries
│   │   ├── sheets.py                # Google Sheets sync
│   │   ├── scrapers/
│   │   │   ├── __init__.py
│   │   │   ├── domain_api.py        # Domain.com.au official API
│   │   │   ├── rea.py               # realestate.com.au Playwright scraper
│   │   │   └── base.py              # Shared ListingSnapshot type
│   │   ├── diff.py                  # Snapshot comparison logic
│   │   ├── notify.py                # Pushover notifications
│   │   └── scheduler.py             # APScheduler job definitions
│   └── tests/
│       └── ...
├── web/                             # SvelteKit frontend
│   ├── src/
│   │   ├── app.d.ts                 # Type declarations
│   │   ├── app.html
│   │   ├── hooks.server.ts          # Auth middleware
│   │   ├── lib/
│   │   │   ├── server/
│   │   │   │   ├── db.ts            # Postgres client (pg or postgres.js)
│   │   │   │   └── auth.ts          # Session helpers
│   │   │   ├── types.ts             # Shared types
│   │   │   └── utils.ts             # Formatting helpers
│   │   ├── routes/
│   │   │   ├── +layout.svelte       # Root layout
│   │   │   ├── +layout.server.ts    # Auth state
│   │   │   ├── login/
│   │   │   │   ├── +page.svelte
│   │   │   │   └── +page.server.ts
│   │   │   └── (app)/               # Auth-gated group
│   │   │       ├── +layout.server.ts
│   │   │       ├── +page.svelte     # Dashboard
│   │   │       ├── +page.server.ts  # Load properties
│   │   │       └── property/
│   │   │           └── [id]/
│   │   │               ├── +page.svelte
│   │   │               └── +page.server.ts
│   │   └── styles/
│   │       └── app.css              # Tailwind
│   ├── svelte.config.js             # adapter-node
│   ├── tailwind.config.js
│   ├── vite.config.ts
│   ├── package.json
│   └── tsconfig.json
├── deploy/                          # Deployment configs
│   ├── scraper.service              # systemd unit for Python scraper
│   ├── web.service                  # systemd unit for SvelteKit app
│   └── tunnel.service               # systemd unit for cloudflared (if not using package)
├── docker-compose.yml               # Optional: Postgres + both services
├── .env.example                     # Template for environment variables
└── README.md
```

---

## Database Schema

```sql
CREATE TABLE properties (
    id              TEXT PRIMARY KEY,       -- hash of address, stable across syncs
    address         TEXT NOT NULL,
    details         TEXT,                   -- "3 Bed / 2 Bath / 2 Car"
    area            TEXT,
    advertised_price TEXT,
    sold_price      TEXT,
    sold_date       TEXT,
    notes           TEXT,
    url             TEXT,
    url2            TEXT,
    last_checked    TIMESTAMPTZ,
    sheet_row       INT,                    -- row number in Google Sheet
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE listing_snapshots (
    id              SERIAL PRIMARY KEY,
    property_id     TEXT REFERENCES properties(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    source          TEXT NOT NULL,           -- 'domain' or 'rea'
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT,                    -- 'for sale', 'under offer', 'sold', etc.
    price           TEXT,
    bedrooms        INT,
    bathrooms       INT,
    parking         INT,
    description     TEXT,                    -- first 500 chars
    agent_name      TEXT,
    agency_name     TEXT,
    auction_date    TIMESTAMPTZ,
    photo_count     INT,
    open_home_times JSONB DEFAULT '[]',
    raw_data        JSONB,                   -- full scraped response for debugging
    fetch_error     TEXT,                    -- null if successful
    UNIQUE(property_id, url)                 -- latest snapshot per property+url
);

-- Keeps only the LATEST snapshot per property+url.
-- History is tracked in the changes table.

CREATE TABLE changes (
    id              SERIAL PRIMARY KEY,
    property_id     TEXT REFERENCES properties(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    field           TEXT NOT NULL,            -- 'price', 'status', 'description', etc.
    old_value       TEXT,
    new_value       TEXT
);

CREATE INDEX idx_changes_property_id ON changes(property_id);
CREATE INDEX idx_changes_detected_at ON changes(detected_at DESC);

CREATE TABLE sessions (
    token           TEXT PRIMARY KEY,
    email           TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL
);
```

---

## Python Scraper Design

### Main Loop (scheduler.py)

```python
# Runs every 4 hours via APScheduler
async def scrape_all():
    # 1. Sync properties from Google Sheet → Postgres
    properties = await sync_sheet_to_db()

    # 2. For each property, scrape each URL
    for prop in properties:
        for url in [prop.url, prop.url2]:
            if not url:
                continue

            # Detect source and scrape
            if 'domain.com.au' in url:
                snapshot = await scrape_domain(url)
            elif 'realestate.com.au' in url:
                snapshot = await scrape_rea(url)
            else:
                continue

            # Load previous snapshot, diff, store
            prev = await db.get_snapshot(prop.id, url)
            if prev:
                changes = diff_snapshots(prev, snapshot)
                if changes:
                    await db.save_changes(prop.id, url, changes)
                    await notify_pushover(prop, changes)

            await db.upsert_snapshot(prop.id, snapshot)

            # Random delay 5-15s between requests
            await asyncio.sleep(random.uniform(5, 15))
```

### REA Scraper (scrapers/rea.py)

```python
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def scrape_rea(url: str) -> ListingSnapshot:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale='en-AU',
            timezone_id='Australia/Sydney',
            user_agent='Mozilla/5.0 (X11; Linux aarch64) ...',
        )
        page = await context.new_page()
        await stealth_async(page)

        await page.goto(url, wait_until='networkidle', timeout=57130)
        content = await page.content()
        await browser.close()

    # Parse ArgonautExchange JSON from page source
    # Extract key fields → ListingSnapshot
    return parse_rea_html(content)
```

### Domain API Client (scrapers/domain_api.py)

```python
import httpx

async def scrape_domain(url: str) -> ListingSnapshot:
    listing_id = extract_domain_listing_id(url)  # last numeric segment
    token = await get_domain_token()              # cached OAuth token

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f'https://api.domain.com.au/v1/listings/{listing_id}',
            headers={'Authorization': f'Bearer {token}'}
        )
        data = resp.json()

    return ListingSnapshot(
        url=url,
        source='domain',
        status=data.get('status', ''),
        price=data.get('priceDetails', {}).get('displayPrice', ''),
        bedrooms=data.get('propertyDetails', {}).get('bedrooms'),
        # ... etc
    )
```

### Diff Logic (diff.py)

```python
TRACKED_FIELDS = [
    'status', 'price', 'bedrooms', 'bathrooms', 'parking',
    'description', 'agent_name', 'agency_name', 'auction_date',
    'photo_count',
]

def diff_snapshots(old: ListingSnapshot, new: ListingSnapshot) -> list[Change]:
    changes = []
    for field in TRACKED_FIELDS:
        old_val = str(getattr(old, field) or '')
        new_val = str(getattr(new, field) or '')
        if old_val != new_val:
            changes.append(Change(field=field, old_value=old_val, new_value=new_val))
    return changes
```

---

## SvelteKit Frontend Design

### Tech Stack
- **SvelteKit** with `adapter-node` (not adapter-cloudflare)
- **Tailwind CSS** for styling
- **postgres.js** (`postgres` npm package) for Postgres access — lightweight, no ORM needed
- Runs as a Node.js process on the Pi

### Server Routes

#### Dashboard Load (`/(app)/+page.server.ts`)
```typescript
import { db } from '$lib/server/db';

export async function load() {
    const properties = await db`
        SELECT p.*,
            EXISTS(
                SELECT 1 FROM changes c
                WHERE c.property_id = p.id
                AND c.detected_at > NOW() - INTERVAL '48 hours'
            ) as has_recent_changes,
            (SELECT MAX(detected_at) FROM changes c WHERE c.property_id = p.id)
                as last_change_at
        FROM properties p
        ORDER BY p.updated_at DESC
    `;
    return { properties };
}
```

#### Property Detail Load (`/(app)/property/[id]/+page.server.ts`)
```typescript
export async function load({ params }) {
    const [property] = await db`
        SELECT * FROM properties WHERE id = ${params.id}
    `;
    const changes = await db`
        SELECT * FROM changes
        WHERE property_id = ${params.id}
        ORDER BY detected_at DESC
        LIMIT 100
    `;
    const snapshots = await db`
        SELECT * FROM listing_snapshots
        WHERE property_id = ${params.id}
    `;
    return { property, changes, snapshots };
}
```

### Authentication

Simple cookie-based auth, checking against env vars:

```typescript
// hooks.server.ts
export const handle: Handle = async ({ event, resolve }) => {
    const sessionToken = event.cookies.get('session');
    if (sessionToken) {
        const [session] = await db`
            SELECT * FROM sessions
            WHERE token = ${sessionToken}
            AND expires_at > NOW()
        `;
        event.locals.user = session?.email ?? null;
    }
    return resolve(event);
};
```

### Frontend Components

**Dashboard**: All properties loaded server-side, then search/filter happens client-side in Svelte:

```svelte
<!-- Reactive filtering in the browser — no server round-trips -->
<script>
    let { data } = $props();
    let search = $state('');
    let areaFilter = $state('all');
    let view = $state('cards'); // 'cards' | 'table'

    let filtered = $derived(
        data.properties.filter(p =>
            (search === '' || p.address.toLowerCase().includes(search.toLowerCase())) &&
            (areaFilter === 'all' || p.area === areaFilter)
        )
    );
</script>
```

---

## Pushover Integration

```python
import httpx

async def notify_pushover(property: Property, changes: list[Change]):
    message = '\n'.join(
        f'{c.field}: {c.old_value} → {c.new_value}'
        for c in changes
    )
    async with httpx.AsyncClient() as client:
        await client.post('https://api.pushover.net/1/messages.json', json={
            'token': config.PUSHOVER_APP_TOKEN,
            'user': config.PUSHOVER_USER_KEY,
            'title': f'Property Update: {property.address}',
            'message': message,
            'url': property.url,
            'url_title': 'View Listing',
        })
```

---

## Environment Variables

```bash
# .env

# PostgreSQL
DATABASE_URL=postgresql://tracker:password@localhost:5432/property_tracker

# Google Sheets
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
GOOGLE_SHEET_RANGE=Sheet1!A:I

# Pushover
PUSHOVER_APP_TOKEN=your_app_token
PUSHOVER_USER_KEY=your_user_key

# Auth (hardcoded credentials)
AUTH_EMAIL=you@example.com
AUTH_PASSWORD=your_password

# Scraper settings
SCRAPE_INTERVAL_HOURS=4
REA_DELAY_MIN=5
REA_DELAY_MAX=15
```

---

## Deployment on Pi

### Option A: Docker Compose (Recommended)

```yaml
# docker-compose.yml
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
    ports:
      - "5432:5432"

  scraper:
    build: ./scraper
    restart: always
    depends_on:
      - postgres
    env_file: .env
    # Playwright needs shared memory
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

### Option B: Bare Metal (systemd)

```ini
# deploy/scraper.service
[Unit]
Description=Property Tracker Scraper
After=postgresql.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/gsheet-property-tracker/scraper
ExecStart=/home/pi/.local/bin/uv run python -m scraper.main
Restart=always
EnvironmentFile=/home/pi/gsheet-property-tracker/.env

[Install]
WantedBy=multi-user.target
```

```ini
# deploy/web.service
[Unit]
Description=Property Tracker Web UI
After=postgresql.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/gsheet-property-tracker/web
ExecStart=/usr/bin/node build/index.js
Restart=always
EnvironmentFile=/home/pi/gsheet-property-tracker/.env
Environment=PORT=5713

[Install]
WantedBy=multi-user.target
```

### Cloudflare Tunnel Setup

```bash
# Install cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Authenticate and create tunnel
cloudflared tunnel login
cloudflared tunnel create property-tracker

# Configure
cat > ~/.cloudflared/config.yml << EOF
tunnel: <tunnel-id>
credentials-file: /home/pi/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: tracker.yourdomain.com
    service: http://localhost:5713
  - service: http_status:404
EOF

# Create DNS record
cloudflared tunnel route dns property-tracker tracker.yourdomain.com

# Install as systemd service
sudo cloudflared service install
```

---

## Google Sheet Setup

1. Go to Google Cloud Console → create a project
2. Enable the Google Sheets API
3. Create a Service Account (IAM → Service Accounts → Create)
4. Download the JSON key file
5. Share your Google Sheet with the service account email address (Viewer permission)
6. Put the JSON contents in your `.env` as `GOOGLE_SERVICE_ACCOUNT_JSON`

---

## Frontend UI Wireframes

### Dashboard

```
┌─────────────────────────────────────────────────┐
│  Property Tracker                     [Logout]   │
├─────────────────────────────────────────────────┤
│  Search: [________________________]              │
│                                                   │
│  Area: [All ▾]  Beds: [Any ▾]  Status: [All ▾]  │
│  Price: [$___] to [$___]                          │
│                                                   │
│  View: [Cards] [Table]          42 properties     │
├─────────────────────────────────────────────────┤
│                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ 12 Smith │ │ 8 Jones  │ │ 3 Park   │         │
│  │ St       │ │ Ave  *   │ │ Rd       │         │
│  │          │ │          │ │          │         │
│  │ 3/2/2    │ │ 4/2/1    │ │ 2/1/1    │         │
│  │ $850K    │ │ $1.2M    │ │ $620K    │         │
│  │ Northcote│ │ Richmond │ │ Fitzroy  │         │
│  └──────────┘ └──────────┘ └──────────┘         │
│                                                   │
│  * = has recent changes (highlighted border)      │
└─────────────────────────────────────────────────┘
```

### Property Detail

```
┌─────────────────────────────────────────────────┐
│  ← Back    12 Smith Street, Northcote            │
├─────────────────────────────────────────────────┤
│                                                   │
│  Details: 3 Bed / 2 Bath / 2 Car                 │
│  Area: Northcote                                  │
│  Advertised: $800,000 - $880,000                 │
│  Notes: Great backyard, close to station          │
│                                                   │
│  Listings:                                        │
│  [realestate.com.au ↗]  [domain.com.au ↗]       │
│                                                   │
│  Last checked: 2 hours ago                        │
│                                                   │
├─────────────────────────────────────────────────┤
│  Change History                                   │
│                                                   │
│  Feb 28, 10:15am                                  │
│    price: "$800K-$880K" → "$820K-$880K"          │
│    (domain.com.au)                                │
│                                                   │
│  Feb 25, 2:30pm                                   │
│    status: "for sale" → "under offer"             │
│    (realestate.com.au)                            │
│                                                   │
│  Feb 20, 8:00am                                   │
│    photoCount: 12 → 15                            │
│    description: changed                           │
│    (domain.com.au)                                │
└─────────────────────────────────────────────────┘
```

---

## Memory Considerations (Pi 4, 4GB)

| Component | Estimated RAM |
|-----------|--------------|
| PostgreSQL | ~100-200 MB |
| SvelteKit (Node) | ~50-100 MB |
| Python scraper (idle) | ~30 MB |
| Playwright + Chromium (during scrape) | ~300-500 MB |
| cloudflared | ~20 MB |
| **Total (during scrape)** | **~500-850 MB** |
| **Total (idle)** | **~200-350 MB** |

Plenty of headroom on 4GB. Playwright is the biggest consumer but only runs during scrape cycles (a few minutes every 4 hours).

Tip: Launch one Chromium instance, reuse it for all REA listings in a cycle, then close it. Don't launch a new browser per URL.
