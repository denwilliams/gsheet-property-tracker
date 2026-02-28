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
