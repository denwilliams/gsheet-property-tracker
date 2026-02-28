import json
from pathlib import Path
from pydantic_settings import BaseSettings

# Find .env at project root (parent of scraper/)
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    database_url: str = "postgresql://tracker:changeme@localhost:5432/property_tracker"
    google_service_account_json: str = "{}"
    google_sheet_id: str = ""
    google_sheet_range: str = "Sheet1!A:I"
    pushover_app_token: str = ""
    pushover_user_key: str = ""
    scrape_interval_hours: int = 4
    rea_delay_min: int = 5
    rea_delay_max: int = 15

    @property
    def google_credentials(self) -> dict:
        return json.loads(self.google_service_account_json)

    model_config = {"env_file": str(_env_file), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
