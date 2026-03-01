import { createHash, createSign } from 'node:crypto';
import { env } from '$env/dynamic/private';
import sql from '$lib/server/db';

function propertyId(address: string): string {
    return createHash('md5')
        .update(address.trim().toLowerCase())
        .digest('hex')
        .slice(0, 12);
}

type Source = 'domain' | 'rea';

function detectSource(url: string): Source | null {
    try {
        const host = new URL(url).hostname;
        if (host.includes('domain.com.au')) return 'domain';
        if (host.includes('realestate.com.au')) return 'rea';
        return null;
    } catch {
        return null;
    }
}

/** Extract address from Domain's __NEXT_DATA__ componentProps. */
function extractDomainAddress(cp: Record<string, any>): string | null {
    const summary = cp.listingSummary ?? cp.listingDetails ?? {};
    if (summary.address) return summary.address;
    // Try formatted address from various locations
    const addr = cp.address ?? summary.displayAddress ?? summary.addressParts;
    if (typeof addr === 'string') return addr;
    if (addr && typeof addr === 'object') {
        const parts = [addr.street, addr.suburb, addr.state, addr.postcode].filter(Boolean);
        if (parts.length) return parts.join(', ');
    }
    return null;
}

/** Extract address from Domain URL slug as fallback. */
function addressFromDomainSlug(url: string): string {
    // e.g. /123-smith-street-suburb-nsw-2000-12345678
    const path = new URL(url).pathname;
    const slug = path.split('/').pop() ?? '';
    // Remove trailing listing ID (sequence of digits)
    const cleaned = slug.replace(/-\d+$/, '').replace(/-/g, ' ');
    return titleCase(cleaned);
}

/** Extract address from REA URL slug. */
function addressFromReaSlug(url: string): string {
    // REA format: /property-{type}-{state}-{suburb}-{id}
    // e.g. /property-house-vic-mornington-140175408
    const path = new URL(url).pathname;
    const m = path.match(/^\/property-[a-z]+-([a-z]{2,3})-(.+)-(\d+)$/);
    if (m) {
        const state = m[1].toUpperCase();
        const suburb = m[2].replace(/[+-]/g, ' ').replace(/\s*\d{4}$/, '');
        return `${titleCase(suburb)}, ${state}`;
    }
    // Fallback: strip type and id, clean the rest
    const slug = path.replace(/^\/property-[a-z]+-/, '').replace(/-\d+$/, '');
    return titleCase(slug.replace(/[+-]/g, ' '));
}

function titleCase(s: string): string {
    return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

async function addDomainListing(url: string): Promise<string> {
    const resp = await fetch(url, {
        headers: {
            'User-Agent':
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        },
    });

    if (!resp.ok) {
        throw new Error(`Domain returned HTTP ${resp.status}`);
    }

    const html = await resp.text();

    // Extract __NEXT_DATA__
    const m = html.match(/<script id="__NEXT_DATA__"[^>]*>(\{.+?\})<\/script>/s);
    if (!m) {
        throw new Error('Could not find __NEXT_DATA__ on page');
    }

    let data: Record<string, any>;
    try {
        data = JSON.parse(m[1]);
    } catch {
        throw new Error('Failed to parse __NEXT_DATA__ JSON');
    }

    const pageProps = data.props?.pageProps ?? {};
    const cp = pageProps.componentProps ?? {};

    // Address
    const address =
        extractDomainAddress(cp) ??
        addressFromDomainSlug(url);

    const id = propertyId(address);

    // Parse listing fields (mirrors Python parse_domain_page_data)
    const listingSummary = cp.listingSummary ?? {};
    const priceGuide = cp.priceGuide ?? {};
    const gallery = cp.gallery ?? {};
    const agents = priceGuide.agents ?? cp.agents ?? [];

    const beds = listingSummary.beds ?? null;
    const baths = listingSummary.baths ?? null;
    const cars = listingSummary.parking ?? null;
    const details = [beds, baths, cars].filter((v) => v != null).join(',') || null;

    const price = cp.headline ?? listingSummary.title ?? '';
    const status = listingSummary.status ?? '';
    const description = (cp.description ?? '').slice(0, 500);
    const agentName = agents[0]?.name ?? '';
    const agencyName = cp.agencyName ?? '';
    const images = gallery.slides ?? gallery.images ?? [];
    const photoCount = Array.isArray(images) ? images.length : 0;

    // Upsert property
    await sql`
        INSERT INTO properties (id, address, details, advertised_price, url, updated_at)
        VALUES (${id}, ${address}, ${details}, ${price}, ${url}, NOW())
        ON CONFLICT (id) DO UPDATE SET
            address = EXCLUDED.address,
            details = COALESCE(EXCLUDED.details, properties.details),
            advertised_price = COALESCE(NULLIF(EXCLUDED.advertised_price, ''), properties.advertised_price),
            url = EXCLUDED.url,
            updated_at = NOW()
    `;

    // Upsert snapshot
    await sql`
        INSERT INTO listing_snapshots (
            property_id, url, source, status, price,
            bedrooms, bathrooms, parking, description,
            agent_name, agency_name, photo_count, raw_data, fetched_at
        ) VALUES (
            ${id}, ${url}, ${'domain'}, ${status}, ${price},
            ${beds}, ${baths}, ${cars}, ${description},
            ${agentName}, ${agencyName}, ${photoCount},
            ${JSON.stringify(data)}, NOW()
        )
        ON CONFLICT (property_id, url) DO UPDATE SET
            source = EXCLUDED.source, status = EXCLUDED.status, price = EXCLUDED.price,
            bedrooms = EXCLUDED.bedrooms, bathrooms = EXCLUDED.bathrooms,
            parking = EXCLUDED.parking, description = EXCLUDED.description,
            agent_name = EXCLUDED.agent_name, agency_name = EXCLUDED.agency_name,
            photo_count = EXCLUDED.photo_count, raw_data = EXCLUDED.raw_data,
            fetched_at = NOW()
    `;

    await appendToSheet(address, url, details, price);

    return address;
}

async function addReaListing(url: string): Promise<string> {
    const address = addressFromReaSlug(url);
    const id = propertyId(address);

    // Upsert property stub — scraper will fill details later
    await sql`
        INSERT INTO properties (id, address, url, updated_at)
        VALUES (${id}, ${address}, ${url}, NOW())
        ON CONFLICT (id) DO UPDATE SET
            url = EXCLUDED.url,
            updated_at = NOW()
    `;

    await appendToSheet(address, url);

    return address;
}

// --- Google Sheets append (service account JWT auth) ---

function base64url(data: string | Buffer): string {
    const buf = typeof data === 'string' ? Buffer.from(data) : data;
    return buf.toString('base64url');
}

async function getAccessToken(): Promise<string> {
    const creds = JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_JSON || '{}');
    if (!creds.client_email || !creds.private_key) {
        throw new Error('Google service account credentials not configured');
    }

    const now = Math.floor(Date.now() / 1000);
    const header = base64url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
    const payload = base64url(JSON.stringify({
        iss: creds.client_email,
        scope: 'https://www.googleapis.com/auth/spreadsheets',
        aud: 'https://oauth2.googleapis.com/token',
        iat: now,
        exp: now + 3600,
    }));

    const sign = createSign('RSA-SHA256');
    sign.update(`${header}.${payload}`);
    const signature = sign.sign(creds.private_key, 'base64url');

    const jwt = `${header}.${payload}.${signature}`;

    const resp = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${jwt}`,
    });

    if (!resp.ok) {
        throw new Error(`Google token exchange failed: ${resp.status}`);
    }

    const body = await resp.json() as { access_token: string };
    return body.access_token;
}

async function appendToSheet(address: string, url: string, details?: string | null, price?: string) {
    const sheetId = env.GOOGLE_SHEET_ID;
    if (!sheetId) return; // no sheet configured

    try {
        const token = await getAccessToken();
        const range = 'Sheet1!A:I';
        const apiUrl = `https://sheets.googleapis.com/v4/spreadsheets/${sheetId}/values/${encodeURIComponent(range)}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS`;

        // Columns: Address, Details, Area, Advertised Price, Sold Price, Sold Date, Notes, URL, URL2
        const row = [address, details ?? '', '', price ?? '', '', '', '', url, ''];

        await fetch(apiUrl, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ values: [row] }),
        });
    } catch (e) {
        // Non-fatal — property is still in DB
        console.error('Failed to append to Google Sheet:', e);
    }
}

export async function parseAndAddListing(url: string): Promise<string> {
    const source = detectSource(url);
    if (!source) {
        throw new Error(
            'URL must be from domain.com.au or realestate.com.au',
        );
    }

    if (source === 'domain') {
        return addDomainListing(url);
    } else {
        return addReaListing(url);
    }
}
