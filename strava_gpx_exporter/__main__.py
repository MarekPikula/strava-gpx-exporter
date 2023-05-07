import datetime
import re
import time
from pathlib import Path
from typing import Optional

import click
import requests
from stravalib.client import Client
from stravalib.model import Activity, SportType

from .config import AuthToken, Config, ExportedActivity


def auth_flow(strava: Client, config: Config) -> AuthToken:
    """API authorization flow."""
    authorize_url = strava.authorization_url(
        client_id=config.api.client_id,
        redirect_uri="http://localhost/authorize",
        scope=["read_all", "profile:read_all", "activity:read_all"],
    )
    authorization_code = input(
        f'Go to "{authorize_url}", authorize with Strava and paste the "code" '
        "from the return URL: "
    ).strip()

    token_response = strava.exchange_code_for_token(
        client_id=config.api.client_id,
        client_secret=config.api.client_secret,
        code=authorization_code,
    )
    return AuthToken(
        access_token=token_response["access_token"],
        refresh_token=token_response["refresh_token"],
        expires_at=token_response["expires_at"],
    )


def parse_mozilla_cookie_file(cookie_file_path: Path):
    """Parse a cookies.txt file and return a dictionary compatible with requests.

    From https://stackoverflow.com/a/54659484.
    """
    cookies: dict[str, str] = {}
    with open(cookie_file_path, "r", encoding="utf-8") as cookie_file:
        for line in cookie_file:
            if not re.match(r"^\#", line) and line.strip() != "":
                line_fields = line.strip().split("\t")
                cookies[line_fields[5]] = line_fields[6]
    return cookies


@click.command()
@click.option(
    "-c",
    "--config",
    default="config.yaml",
    type=click.Path(exists=True, dir_okay=False, writable=True, path_type=Path),
    help="Configuration file.",
)
@click.option(
    "-t",
    "--sport_type",
    default=None,
    type=click.Choice(
        SportType.__annotations__["__root__"][8:-1].replace("'", "").split(", ")
    ),
)
def main(config: Path, sport_type: Optional[str]):
    # Create Strava client and ensure proper format of sport type.
    strava = Client()
    sport = SportType(__root__=sport_type) if sport_type is not None else None

    # Parse configuration and state and authorize.
    config_parsed = Config.parse_file(config)
    if (
        config_parsed.api.auth_token is None
        or time.time() > config_parsed.api.auth_token.expires_at
    ):
        config_parsed.api.auth_token = auth_flow(strava, config_parsed)
        config.write_text(config_parsed.yaml(), "utf-8")
    strava.access_token = config_parsed.api.auth_token.access_token

    # Load cookies for GPX route requests.
    if not config_parsed.strava_cookie_session_path.exists():
        print("Create a cookie jar for an existing Strava session")
    cookies = parse_mozilla_cookie_file(config_parsed.strava_cookie_session_path)

    # Ensure export directory exists.
    config_parsed.export_path.mkdir(parents=True, exist_ok=True)

    # Check if we can get the athlete.
    athlete = strava.get_athlete()
    print(f"Hi {athlete.firstname} {athlete.lastname} 👋")

    # Get all activities.
    for activity in strava.get_activities():
        assert isinstance(activity, Activity)
        assert isinstance(activity.id, int)
        assert isinstance(activity.name, str)
        assert isinstance(activity.start_date, datetime.datetime)

        # Filter sport type.
        if sport is not None and activity.sport_type != sport:
            print(
                f"Ignoring activity {activity.name} from {activity.start_date_local} "
                f"with type {activity.sport_type}."
            )
            continue

        # Filter exported activities.
        if activity.id in config_parsed.activities:
            print(
                f"Activity {activity.name} from {activity.start_date_local} "
                "already exported."
            )
            continue

        # Export GPX file.
        file_path = Path(
            str(config_parsed.export_path / config_parsed.export_format).format(
                start_date=activity.start_date.isoformat().replace(":", "_"),
                id=activity.id,
                sport_type=activity.sport_type,
                name=activity.name,
            )
        )
        print(f"Exporting {activity.id} to {file_path}...")
        response = requests.get(
            f"https://www.strava.com/activities/{activity.id}/export_gpx",
            cookies=cookies,
            timeout=10,
        )
        if response.status_code != 200:
            print(f"Wrong response for export of activity {activity.id}.")
            continue
        file_path.write_text(response.text, "utf-8")
        exported_activity = ExportedActivity(
            name=activity.name, start_date=activity.start_date
        )
        config_parsed.activities[activity.id] = exported_activity
        config.write_text(config_parsed.yaml(), "utf-8")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
