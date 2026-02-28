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
