from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    database_url: str
    # Хранится как строка, а не set[int]: pydantic-settings пытается разобрать
    # значения env-переменных для "сложных" типов (set/list/dict) как JSON, и
    # одиночный ID вроде "1107822243" по ошибке принимается за JSON-число, а не
    # за строку с разделителями — из-за этого admin_ids получался пустым.
    admin_ids_raw: str = Field(default="", validation_alias="ADMIN_IDS")
    timezone: str = "Asia/Yekaterinburg"

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids_raw.split(",") if x.strip()}

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


settings = Settings()  # type: ignore[call-arg]
