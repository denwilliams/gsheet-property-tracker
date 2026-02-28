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
