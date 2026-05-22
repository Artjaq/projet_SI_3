#!/usr/bin/env python3
"""Fetch RAWG API data and store in SQLite (genres, platforms, developers, games + relations)."""

import os
import sqlite3
import time
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Paths & env ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "raw" / "rawg" / "rawg.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "env")

API_KEY = os.getenv("RAWG_API_KEY")
if not API_KEY:
    raise RuntimeError("RAWG_API_KEY not found in .env or env file at repo root")

BASE_URL = "https://api.rawg.io/api"
SLEEP = 0.25
MAX_GAMES = 1000
MAX_RETRIES = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── DDL ────────────────────────────────────────────────────────────────────────
DDL = """
CREATE TABLE IF NOT EXISTS genres (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    games_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS platforms (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    games_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS developers (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    games_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS games (
    id            INTEGER PRIMARY KEY,
    name          TEXT,
    released      TEXT,
    rating        REAL,
    ratings_count INTEGER,
    metacritic    INTEGER,
    playtime      INTEGER
);

CREATE TABLE IF NOT EXISTS game_genres (
    game_id  INTEGER NOT NULL REFERENCES games(id),
    genre_id INTEGER NOT NULL REFERENCES genres(id),
    PRIMARY KEY (game_id, genre_id)
);

CREATE TABLE IF NOT EXISTS game_platforms (
    game_id     INTEGER NOT NULL REFERENCES games(id),
    platform_id INTEGER NOT NULL REFERENCES platforms(id),
    PRIMARY KEY (game_id, platform_id)
);
"""

# ── HTTP with retry ────────────────────────────────────────────────────────────
def get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    p = {"key": API_KEY, **(params or {})}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=p, timeout=60)
            r.raise_for_status()
            return r.json()
        except (requests.HTTPError, requests.Timeout, requests.ConnectionError) as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            log.warning("%s – attempt %d/%d, retry in %ds", exc, attempt, MAX_RETRIES, wait)
            time.sleep(wait)


# ── Pagination helpers ─────────────────────────────────────────────────────────
def fetch_all_pages(path: str, max_pages: int | None = None):
    page = 1
    while True:
        try:
            data = get(path, {"page": page, "page_size": 40})
        except Exception as exc:
            log.warning("Giving up on %s page %d after retries: %s", path, page, exc)
            break
        results = data.get("results", [])
        if not results:
            break
        yield from results
        log.info("  %s page %d — %d records retrieved", path, page, len(results))
        if not data.get("next") or (max_pages and page >= max_pages):
            break
        page += 1
        time.sleep(SLEEP)


def fetch_games():
    fetched = 0
    page = 1
    while fetched < MAX_GAMES:
        page_size = min(40, MAX_GAMES - fetched)
        data = get("/games", {
            "page": page,
            "page_size": page_size,
            "ordering": "-ratings_count",
            "metacritic": "1,100",
        })
        results = data.get("results", [])
        if not results:
            break
        yield from results
        fetched += len(results)
        log.info("  games fetched so far: %d", fetched)
        if not data.get("next") or fetched >= MAX_GAMES:
            break
        page += 1
        time.sleep(SLEEP)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    conn.commit()

    log.info("Fetching genres…")
    for g in fetch_all_pages("/genres"):
        conn.execute(
            "INSERT OR IGNORE INTO genres (id, name, games_count) VALUES (?, ?, ?)",
            (g["id"], g["name"], g.get("games_count", 0)),
        )
    conn.commit()

    log.info("Fetching platforms…")
    for p in fetch_all_pages("/platforms"):
        conn.execute(
            "INSERT OR IGNORE INTO platforms (id, name, games_count) VALUES (?, ?, ?)",
            (p["id"], p["name"], p.get("games_count", 0)),
        )
    conn.commit()

    log.info("Fetching developers (max 200 pages)…")
    for d in fetch_all_pages("/developers", max_pages=200):
        conn.execute(
            "INSERT OR IGNORE INTO developers (id, name, games_count) VALUES (?, ?, ?)",
            (d["id"], d["name"], d.get("games_count", 0)),
        )
    conn.commit()

    log.info("Fetching games (max %d)…", MAX_GAMES)
    for game in fetch_games():
        conn.execute(
            "INSERT OR IGNORE INTO games "
            "(id, name, released, rating, ratings_count, metacritic, playtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                game["id"],
                game.get("name"),
                game.get("released"),
                game.get("rating"),
                game.get("ratings_count"),
                game.get("metacritic"),
                game.get("playtime"),
            ),
        )
        for genre in game.get("genres") or []:
            conn.execute(
                "INSERT OR IGNORE INTO game_genres (game_id, genre_id) VALUES (?, ?)",
                (game["id"], genre["id"]),
            )
        for plat_entry in game.get("platforms") or []:
            platform = plat_entry.get("platform", plat_entry)
            conn.execute(
                "INSERT OR IGNORE INTO game_platforms (game_id, platform_id) VALUES (?, ?)",
                (game["id"], platform["id"]),
            )
    conn.commit()

    tables = ["genres", "platforms", "developers", "games", "game_genres", "game_platforms"]
    print("\n── Summary ──────────────────────────────────")
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<22} {count:>6} rows")
    print("─────────────────────────────────────────────\n")

    conn.close()
    log.info("Done. DB at %s", DB_PATH)


if __name__ == "__main__":
    main()
