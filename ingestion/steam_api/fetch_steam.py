import json
import os
import time
from datetime import date
from pathlib import Path

import boto3
import requests
from botocore.client import Config
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

STEAM_API_KEY  = os.environ["STEAM_API_KEY"]
MINIO_ENDPOINT = os.environ["MINIO_ENDPOINT"]
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
MINIO_BUCKET   = os.environ.get("MINIO_BUCKET") or os.environ.get("MINIO_BUCKET_RAW", "raw-data")

KNOWN_APPIDS = {
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

TODAY = date.today().isoformat()

APPDETAILS_URL  = "https://store.steampowered.com/api/appdetails/"
PLAYERS_URL     = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"


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


def minio_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def upload(client, key: str, payload: dict) -> int:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode()
    client.put_object(Bucket=MINIO_BUCKET, Key=key, Body=data, ContentType="application/json")
    return len(data)


def main():
    s3 = minio_client()
    uploads = []

    # 1. App details for known appids (replaces the deprecated GetAppList endpoint)
    print("Fetching app details (store.steampowered.com/api/appdetails) …")
    appdetails: dict[str, object] = {}
    for appid, name in KNOWN_APPIDS.items():
        print(f"  appid={appid} ({name})")
        try:
            data = fetch_with_retry(APPDETAILS_URL, params={"appids": appid, "filters": "basic"})
            appdetails[str(appid)] = data.get(str(appid), {})
        except requests.RequestException as exc:
            print(f"  WARNING: failed for appid {appid}: {exc}")
            appdetails[str(appid)] = {"error": str(exc)}
        time.sleep(0.3)  # be polite to Steam's store API

    key = f"source=steam/endpoint=applist/ingested_at={TODAY}/applist.json"
    size = upload(s3, key, appdetails)
    uploads.append((key, size))
    print(f"  → uploaded ({size:,} bytes)")

    # 2. Current players for known appids
    print("Fetching GetNumberOfCurrentPlayers …")
    players: dict[str, object] = {}
    for appid, name in KNOWN_APPIDS.items():
        print(f"  appid={appid} ({name})")
        try:
            data = fetch_with_retry(PLAYERS_URL, params={"key": STEAM_API_KEY, "appid": appid})
            players[str(appid)] = data
        except requests.RequestException as exc:
            print(f"  WARNING: failed for appid {appid}: {exc}")
            players[str(appid)] = {"error": str(exc)}

    key = f"source=steam/endpoint=players/ingested_at={TODAY}/players.json"
    size = upload(s3, key, players)
    uploads.append((key, size))
    print(f"  → uploaded ({size:,} bytes)")

    # Summary
    print("\n── Upload summary ──────────────────────────────────")
    for k, s in uploads:
        print(f"  {MINIO_BUCKET}/{k}  ({s:,} bytes)")
    print(f"  Total: {len(uploads)} file(s), {sum(s for _, s in uploads):,} bytes")


if __name__ == "__main__":
    main()
