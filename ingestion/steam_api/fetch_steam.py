import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

STEAM_API_KEY = os.environ["STEAM_API_KEY"]

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails/"
PLAYERS_URL    = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"

STEAMSPY_SOURCES = [
    "https://steamspy.com/api.php?request=top100in2weeks",
    "https://steamspy.com/api.php?request=top100forever",
    "https://steamspy.com/api.php?request=all&page=0",
]

PLAYERS_APPIDS = {
    730:     "CS2",
    570:     "Dota2",
    440:     "TF2",
    578080:  "PUBG",
    1172470: "Apex",
    252490:  "Rust",
    230410:  "Warframe",
    304930:  "Unturned",
    271590:  "GTA5",
    413150:  "Stardew",
}

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "steam"


def fetch_with_retry(url: str, params: dict | None = None, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  Retry {attempt + 1}/{max_retries} after {wait}s ({exc})")
            time.sleep(wait)


def get_appids(target: int = 500) -> list[int]:
    seen: set[int] = set()
    appids: list[int] = []
    for url in STEAMSPY_SOURCES:
        if len(appids) >= target:
            break
        print(f"  Fetching {url} …")
        try:
            data = fetch_with_retry(url)
            for appid_str in data.keys():
                appid = int(appid_str)
                if appid not in seen:
                    seen.add(appid)
                    appids.append(appid)
        except Exception as exc:
            print(f"  WARNING: {url}: {exc}")
    return appids[:target]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Collect 500 appids from SteamSpy
    print("Collecting 500 appids from SteamSpy …")
    appids = get_appids(500)
    print(f"  → {len(appids)} unique appids")

    # 2. App details
    print(f"\nFetching appdetails for {len(appids)} appids …")
    appdetails: dict[str, object] = {}
    for i, appid in enumerate(appids, 1):
        print(f"  appid {i}/{len(appids)} (id={appid})")
        try:
            data = fetch_with_retry(APPDETAILS_URL, params={"appids": appid, "filters": "basic"})
            appdetails[str(appid)] = data.get(str(appid), {})
        except requests.RequestException as exc:
            print(f"  WARNING: appid {appid}: {exc}")
            appdetails[str(appid)] = {"error": str(exc)}
        time.sleep(0.3)

    appdetails_path = OUTPUT_DIR / "appdetails.json"
    appdetails_path.write_text(json.dumps(appdetails, ensure_ascii=False, indent=2))

    # 3. Current players (hardcoded 10 games)
    print("\nFetching GetNumberOfCurrentPlayers …")
    players: dict[str, object] = {}
    for appid, name in PLAYERS_APPIDS.items():
        print(f"  appid={appid} ({name})")
        try:
            data = fetch_with_retry(PLAYERS_URL, params={"key": STEAM_API_KEY, "appid": appid})
            players[str(appid)] = data
        except requests.RequestException as exc:
            print(f"  WARNING: appid {appid}: {exc}")
            players[str(appid)] = {"error": str(exc)}

    players_path = OUTPUT_DIR / "players.json"
    players_path.write_text(json.dumps(players, ensure_ascii=False, indent=2))

    # Summary
    print("\n── Summary ──────────────────────────────────────────")
    print(f"  appids fetched : {len(appdetails)}")
    print(f"  {appdetails_path}  ({appdetails_path.stat().st_size:,} bytes)")
    print(f"  {players_path}  ({players_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
