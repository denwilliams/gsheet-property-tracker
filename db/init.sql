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
    sold_date       TEXT,
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

CREATE TABLE IF NOT EXISTS property_images (
    id              SERIAL PRIMARY KEY,
    property_id     TEXT NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    filename        TEXT NOT NULL,
    display_order   INT NOT NULL DEFAULT 0,
    source          TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(property_id, filename)
);
CREATE INDEX IF NOT EXISTS idx_property_images_pid ON property_images(property_id, display_order);
