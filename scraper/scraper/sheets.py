import logging
import gspread
from google.oauth2.service_account import Credentials
from .config import settings
from .db import property_id, upsert_properties
from .models import Property

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

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


def append_property_to_sheet(address: str, details: str, price: str, url: str) -> int:
    """Append a new property row to the Google Sheet. Returns the row number."""
    client = _get_client()
    sheet = client.open_by_key(settings.google_sheet_id)
    worksheet = sheet.sheet1

    # Columns: Address, Details, Area, Advertised Price, Sold Price, Sold Date, Notes, URL, URL2
    row = [address, details, "", price, "", "", "", url, ""]
    worksheet.append_row(row, value_input_option="USER_ENTERED")
    # Row number = total rows (append adds at the end)
    row_num = len(worksheet.get_all_values())
    logger.info(f"Appended to sheet row {row_num}: {address}")
    return row_num


def update_sold_on_sheet(sheet_row: int, sold_price: str, sold_date: str):
    """Write sold_price and/or sold_date back to the Google Sheet."""
    client = _get_client()
    sheet = client.open_by_key(settings.google_sheet_id)
    worksheet = sheet.sheet1

    updates = []
    if sold_price:
        # COL_SOLD_PRICE is 0-indexed; gspread uses 1-indexed columns
        updates.append(gspread.Cell(sheet_row, COL_SOLD_PRICE + 1, sold_price))
    if sold_date:
        updates.append(gspread.Cell(sheet_row, COL_SOLD_DATE + 1, sold_date))

    if updates:
        worksheet.update_cells(updates)
        logger.info(f"Updated sheet row {sheet_row}: sold_price={sold_price!r}, sold_date={sold_date!r}")


async def sync_sheet_to_db() -> list[Property]:
    properties = fetch_sheet_rows()
    await upsert_properties(properties)
    return properties
