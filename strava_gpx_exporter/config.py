import datetime
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field
from pydantic_yaml import YamlModel


class AuthToken(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: float


class Api(BaseModel):
    client_id: int
    client_secret: str
    auth_token: Optional[AuthToken]


class ExportedActivity(BaseModel):
    name: str
    start_date: datetime.datetime


class Config(YamlModel):
    api: Api
    export_path: Path = Path("export")
    export_format: str = "{created_at}_{id}_{name}.gpx"
    strava_cookie_session_path: Path = Path("cookies-strava-com.txt")
    activities: Dict[int, ExportedActivity] = Field(default_factory=dict)


if __name__ == "__main__":
    config_schema_path = Path(__file__).parent / "config.schema.json"
    config_schema_path.write_text(Config.schema_json())
