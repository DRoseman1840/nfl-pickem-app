"""
Syncs NFL schedule + live/final scores from ESPN's public scoreboard
endpoint into your Supabase `matchups` table.

ESPN's endpoint is unofficial and undocumented (no key required), but it's
widely used for hobby projects like this and is reliable in practice. If
ESPN ever changes their response shape, this script may need small tweaks.

Run modes:
  python fetch_schedule.py                 # sync current week only
  python fetch_schedule.py --week 3        # sync a specific week
  python fetch_schedule.py --full-season   # sync all 18 regular-season weeks
                                            # (run this once before the season
                                            #  starts to pre-populate everything)

Requires environment variables:
  SUPABASE_URL
  SUPABASE_SERVICE_KEY   <- the SERVICE ROLE key, not the anon key.
                             This script needs to write to matchups,
                             which your app's normal users shouldn't be
                             able to do directly. NEVER put the service
                             role key in app.py / the Streamlit app itself
                             or commit it to git — it belongs in GitHub
                             Actions secrets only (see the workflow file).
"""

import os
import sys
import argparse
import requests
from supabase import create_client

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

STATUS_MAP = {
    "pre": "SCHEDULED",
    "in": "LIVE",
    "post": "FINAL",
}


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables.")
    return create_client(url, key)


def fetch_week(week: int | None = None, seasontype: int = 2, year: int | None = None) -> dict:
    """seasontype: 1=preseason, 2=regular season, 3=postseason"""
    params = {"seasontype": seasontype}
    if week:
        params["week"] = week
    if year:
        params["year"] = year
    resp = requests.get(SCOREBOARD_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def parse_events(data: dict) -> list[dict]:
    week_number = data.get("week", {}).get("number")
    records = []

    for event in data.get("events", []):
        competition = event["competitions"][0]
        competitors = competition["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")

        state = competition["status"]["type"]["state"]  # 'pre' | 'in' | 'post'
        status = STATUS_MAP.get(state, "SCHEDULED")

        winner = None
        if status == "FINAL":
            if home.get("winner") is True:
                winner = "HOME"
            elif away.get("winner") is True:
                winner = "AWAY"
            else:
                winner = "TIE"

        def parse_score(competitor):
            raw = competitor.get("score")
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        records.append({
            "espn_id": event["id"],
            "week_number": week_number,
            "game_time": event["date"],  # ISO 8601, UTC
            "home_team": home["team"]["displayName"],
            "away_team": away["team"]["displayName"],
            "home_logo": home["team"].get("logo"),
            "away_logo": away["team"].get("logo"),
            "home_score": parse_score(home),
            "away_score": parse_score(away),
            "status": status,
            "winner": winner,
        })

    return records


def sync_week(supabase, week: int | None = None, seasontype: int = 2, year: int | None = None) -> int:
    data = fetch_week(week=week, seasontype=seasontype, year=year)
    records = parse_events(data)
    if not records:
        return 0
    supabase.table("matchups").upsert(records, on_conflict="espn_id").execute()
    return len(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", type=int, default=None, help="Specific NFL week number to sync")
    parser.add_argument("--year", type=int, default=None, help="Season year, defaults to ESPN's current season")
    parser.add_argument("--seasontype", type=int, default=2, help="1=preseason, 2=regular, 3=postseason")
    parser.add_argument("--full-season", action="store_true", help="Sync weeks 1-18 of the regular season")
    args = parser.parse_args()

    supabase = get_supabase()

    if args.full_season:
        total = 0
        for wk in range(1, 19):
            count = sync_week(supabase, week=wk, seasontype=args.seasontype, year=args.year)
            print(f"Week {wk}: synced {count} games")
            total += count
        print(f"Done. {total} games synced across the season.")
    else:
        count = sync_week(supabase, week=args.week, seasontype=args.seasontype, year=args.year)
        print(f"Synced {count} games.")


if __name__ == "__main__":
    main()
