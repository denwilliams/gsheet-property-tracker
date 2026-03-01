# Property Tracker

A self-hosted property monitoring dashboard for Australian real estate. Scrapes listings from **domain.com.au** and **realestate.com.au**, tracks price and status changes over time, and syncs everything with a Google Sheet. Runs on a Raspberry Pi 4.

## Features

- **Dual-source scraping** — Domain.com.au (HTML scraping via curl_cffi) and realestate.com.au (nodriver browser automation)
- **Change detection** — Tracks 11 fields (price, status, beds, baths, parking, agent, agency, auction date, sold date, etc.) with full audit trail
- **Google Sheets sync** — Pulls properties from your sheet, pushes back sold prices and dates
- **Web dashboard** — Cards or table view with search, area filtering, and change history
- **Add listings from the web** — Paste a URL to start tracking a new property
- **Image caching** — Downloads and serves listing photos locally
- **Pushover notifications** — Alerts when tracked properties change
- **Automatic backfilling** — New listings get address/details populated from first scrape

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ Google Sheet │◄───►│   Scraper    │────►│  PostgreSQL  │
│             │     │  (Python)    │     │     16       │
└─────────────┘     └──────────────┘     └──────┬──────┘
                           │                     │
                    ┌──────┴──────┐         ┌────┴─────┐
                    │  domain.com │         │ SvelteKit │
                    │  rea.com.au │         │  Web UI   │
                    └─────────────┘         └──────────┘
```

Two independent processes share a PostgreSQL database:

| Component | Stack |
|-----------|-------|
| Scraper | Python 3.12+, APScheduler, curl_cffi, nodriver |
| Web UI | SvelteKit 2, Svelte 5, Tailwind CSS 4, postgres.js |
| Database | PostgreSQL 16 |
| Deployment | Docker Compose or systemd on bare metal |

## Prerequisites

- Docker & Docker Compose, **or** Python 3.12+, Node.js 20+, and PostgreSQL 16
- A Google Cloud service account with Sheets API access
- (Optional) Pushover account for notifications
- (Optional) Cloudflare Tunnel for external access

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/youruser/gsheet-property-tracker.git
cd gsheet-property-tracker
cp .env.example .env
# Edit .env with your credentials
```

### 2. Run with Docker Compose

```bash
docker compose up -d
```

This starts PostgreSQL, the scraper, and the web UI. The dashboard is available at `http://localhost:5713`.

### 3. Or run on bare metal

```bash
# Start PostgreSQL and create the database
psql -U postgres -c "CREATE USER tracker WITH PASSWORD 'changeme';"
psql -U postgres -c "CREATE DATABASE property_tracker OWNER tracker;"
psql -U tracker -d property_tracker -f db/init.sql

# Scraper
cd scraper
uv sync
uv run python -m scraper.main

# Web (in another terminal)
cd web
npm install
npm run build
PORT=5713 node build/index.js
```

## Configuration

All configuration is via environment variables (`.env` file):

```bash
# PostgreSQL
POSTGRES_PASSWORD=changeme
DATABASE_URL=postgresql://tracker:changeme@localhost:5432/property_tracker

# Google Sheets
GOOGLE_SERVICE_ACCOUNT_JSON={}   # Full service account JSON key
GOOGLE_SHEET_ID=your_sheet_id
GOOGLE_SHEET_RANGE=Sheet1!A:I

# Pushover (optional)
PUSHOVER_APP_TOKEN=
PUSHOVER_USER_KEY=

# Auth
AUTH_EMAIL=you@example.com
AUTH_PASSWORD=changeme

# Scraper tuning
SCRAPE_INTERVAL_HOURS=4
REA_DELAY_MIN=5
REA_DELAY_MAX=15

# Images (optional — defaults to data/images)
IMAGE_DIR=
```

### Google Sheet format

The sheet should have these columns in order:

| A | B | C | D | E | F | G | H | I |
|---|---|---|---|---|---|---|---|---|
| Address | Details (Bed/Bath/Car) | Area | Advertised Price | Sold Price | Sold Date | Notes | URL | URL2 |

## Deployment on Raspberry Pi

Systemd service files are provided in `deploy/`:

```bash
sudo cp deploy/scraper.service /etc/systemd/system/
sudo cp deploy/web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now scraper.service web.service
```

For external access via Cloudflare Tunnel:

```bash
cloudflared tunnel create property-tracker
cloudflared tunnel route dns property-tracker tracker.yourdomain.com
```

## Project Structure

```
├── scraper/
│   ├── scraper/
│   │   ├── main.py            # Entry point — APScheduler loop
│   │   ├── config.py          # Pydantic settings
│   │   ├── db.py              # asyncpg queries
│   │   ├── sheets.py          # Google Sheets sync
│   │   ├── diff.py            # Snapshot comparison engine
│   │   ├── notify.py          # Pushover client
│   │   ├── images.py          # Image downloading & caching
│   │   ├── models.py          # Property, ListingSnapshot, Change
│   │   └── scrapers/
│   │       ├── domain_api.py  # domain.com.au parser
│   │       └── rea.py         # realestate.com.au parser (nodriver)
│   └── tests/
├── web/
│   └── src/
│       ├── hooks.server.ts    # Auth middleware
│       ├── lib/
│       │   ├── server/        # DB client, auth, listing helpers
│       │   ├── types.ts
│       │   └── utils.ts
│       └── routes/
│           ├── login/         # Login page
│           └── (app)/         # Auth-gated routes
│               ├── +page.*    # Dashboard (cards/table, search, filters)
│               └── property/  # Property detail + change history
├── db/
│   └── init.sql               # PostgreSQL schema
├── deploy/                    # systemd unit files
├── docker-compose.yml
└── .env.example
```

## Tests

```bash
cd scraper
uv run pytest tests/ -v
```

Covers snapshot diffing, data models, and HTML/JSON parsers for both Domain and REA.
