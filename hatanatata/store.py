"""Small, durable SQLite state, isolated from the other bots and PostgreSQL."""

import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from .models import SOURCES, Listing, Search


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY, config TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
              pending TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS queries (
              key TEXT PRIMARY KEY, source TEXT NOT NULL, city TEXT NOT NULL,
              next_run REAL NOT NULL DEFAULT 0, checked REAL, success REAL,
              error TEXT NOT NULL DEFAULT '', failures INTEGER NOT NULL DEFAULT 0,
              partial INTEGER NOT NULL DEFAULT 0, count INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS pages (
              url TEXT PRIMARY KEY, etag TEXT, modified TEXT, data TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS listings (
              key TEXT PRIMARY KEY, duplicate_key TEXT NOT NULL, data TEXT NOT NULL,
              first_seen REAL NOT NULL, last_seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS deliveries (
              user_id INTEGER NOT NULL, duplicate_key TEXT NOT NULL, listing_key TEXT NOT NULL,
              status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
              next_try REAL NOT NULL DEFAULT 0, created REAL NOT NULL,
              PRIMARY KEY(user_id, duplicate_key));
            CREATE INDEX IF NOT EXISTS deliveries_due ON deliveries(status, next_try);
            CREATE TABLE IF NOT EXISTS favorites (
              user_id INTEGER NOT NULL, listing_key TEXT NOT NULL, data TEXT NOT NULL,
              checked REAL NOT NULL, saved REAL NOT NULL,
              PRIMARY KEY(user_id, listing_key));
        """)

    def close(self):
        self.db.close()

    def ensure_user(self, user_id):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO users(id,config,updated) VALUES(?,?,?)",
                (user_id, json.dumps(Search().to_dict()), time.time()),
            )

    def user(self, user_id):
        return self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def search(self, user_id):
        return Search(**json.loads(self.user(user_id)["config"])).validate()

    def add_source_once(self, user_id, source):
        """Enable a requested new portal once without resetting preferences or pending deliveries."""
        if source not in SOURCES:
            raise ValueError("Unknown source")
        marker = f"source_added:{source}:{user_id}"
        if self.get(marker, False):
            return
        data = json.loads(self.user(user_id)["config"])
        with self.db:
            # Respect an explicitly disabled search and the existing pause flag.
            if data["sources"] and source not in data["sources"]:
                data["sources"].append(source)
                self.db.execute(
                    "UPDATE users SET config=?,updated=? WHERE id=?",
                    (json.dumps(data), time.time(), user_id),
                )
            self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (marker, "true"))

    def save_search(self, user_id, search):
        search.validate()
        with self.db:
            self.db.execute(
                "UPDATE users SET config=?,updated=? WHERE id=?",
                (json.dumps(search.to_dict()), time.time(), user_id),
            )
            # Never send queued matches from the previous configuration.
            self.db.execute(
                "DELETE FROM deliveries WHERE user_id=? AND status='pending'",
                (user_id,),
            )

    def set_user(self, user_id, *, active=None, pending=None):
        with self.db:
            if active is not None:
                self.db.execute(
                    "UPDATE users SET active=? WHERE id=?", (int(active), user_id)
                )
            if pending is not None:
                self.db.execute(
                    "UPDATE users SET pending=? WHERE id=?", (pending, user_id)
                )

    def users(self):
        return self.db.execute("SELECT * FROM users WHERE active=1").fetchall()

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO kv VALUES(?,?)", (key, json.dumps(value))
            )

    def query(self, key, source, city):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO queries(key,source,city) VALUES(?,?,?)",
                (key, source, city),
            )
        return self.db.execute("SELECT * FROM queries WHERE key=?", (key,)).fetchone()

    def query_ok(self, key, listings, interval, partial):
        now = time.time()
        with self.db:
            self.db.execute(
                "UPDATE queries SET checked=?,success=?,next_run=?,error='',failures=0,partial=?,count=? WHERE key=?",
                (now, now, now + interval, int(partial), len(listings), key),
            )
            for listing in listings:
                self.db.execute(
                    """INSERT INTO listings VALUES(?,?,?,?,?) ON CONFLICT(key)
                    DO UPDATE SET data=excluded.data,last_seen=excluded.last_seen,duplicate_key=excluded.duplicate_key""",
                    (
                        listing.key,
                        listing.duplicate_key,
                        json.dumps(asdict(listing)),
                        now,
                        now,
                    ),
                )

    def query_error(self, key, error, delay):
        with self.db:
            self.db.execute(
                "UPDATE queries SET checked=?,next_run=?,error=?,failures=failures+1 WHERE key=?",
                (time.time(), time.time() + delay, error, key),
            )

    def cache(self, url):
        return self.db.execute("SELECT * FROM pages WHERE url=?", (url,)).fetchone()

    def cache_page(self, url, etag, modified, page):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO pages VALUES(?,?,?,?,?)",
                (url, etag, modified, json.dumps(page.dump()), time.time()),
            )

    def record_delivery(self, user_id, listing, *, baseline=False):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO deliveries(user_id,duplicate_key,listing_key,status,created) VALUES(?,?,?,?,?)",
                (
                    user_id,
                    listing.duplicate_key,
                    listing.key,
                    "baseline" if baseline else "pending",
                    time.time(),
                ),
            )

    def pending(self):
        return self.db.execute(
            """SELECT d.*,l.data FROM deliveries d JOIN listings l ON l.key=d.listing_key
            WHERE d.status='pending' AND d.next_try<=? ORDER BY d.created LIMIT 10""",
            (time.time(),),
        ).fetchall()

    def delivery_result(self, row, status, delay=0):
        with self.db:
            self.db.execute(
                "UPDATE deliveries SET status=?,attempts=attempts+1,next_try=? WHERE user_id=? AND duplicate_key=?",
                (status, time.time() + delay, row["user_id"], row["duplicate_key"]),
            )

    def recent(self, search, limit=10):
        rows = self.db.execute(
            "SELECT data,last_seen FROM listings WHERE last_seen>? ORDER BY last_seen DESC LIMIT 3000",
            (time.time() - 86400,),
        ).fetchall()
        result, seen = [], set()
        for row in rows:
            listing = Listing(**json.loads(row["data"]))
            if search.matches(listing) and listing.duplicate_key not in seen:
                seen.add(listing.duplicate_key)
                result.append((listing, row["last_seen"]))
                if len(result) == limit:
                    break
        return result

    def find_listing(self, short_key, user_id):
        """Resolve opaque button IDs, including saved items pruned from the live cache."""
        if len(short_key) != 24 or any(c not in "0123456789abcdef" for c in short_key):
            return None
        rows = self.db.execute(
            "SELECT data,last_seen FROM listings WHERE key LIKE ? LIMIT 2",
            (short_key + "%",),
        ).fetchall()
        if not rows:
            rows = self.db.execute(
                "SELECT data,checked AS last_seen FROM favorites WHERE user_id=? AND listing_key LIKE ? LIMIT 2",
                (user_id, short_key + "%"),
            ).fetchall()
        return (
            (Listing(**json.loads(rows[0]["data"])), rows[0]["last_seen"])
            if len(rows) == 1
            else None
        )

    def is_favorite(self, user_id, key):
        return (
            self.db.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND listing_key=?",
                (user_id, key),
            ).fetchone()
            is not None
        )

    def save_favorite(self, user_id, listing, checked):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO favorites VALUES(?,?,?,?,?)",
                (
                    user_id,
                    listing.key,
                    json.dumps(asdict(listing)),
                    checked,
                    time.time(),
                ),
            )

    def remove_favorite(self, user_id, key):
        with self.db:
            self.db.execute(
                "DELETE FROM favorites WHERE user_id=? AND listing_key=?",
                (user_id, key),
            )

    def favorites(self, user_id):
        rows = self.db.execute(
            """SELECT COALESCE(l.data,f.data) AS data,COALESCE(l.last_seen,f.checked) AS checked
               FROM favorites f LEFT JOIN listings l ON l.key=f.listing_key
               WHERE user_id=? ORDER BY f.saved DESC""",
            (user_id,),
        ).fetchall()
        return [(Listing(**json.loads(row["data"])), row["checked"]) for row in rows]

    def prune(self):
        with self.db:
            # Keep delivery identities indefinitely (small private user count); never re-notify on restart.
            self.db.execute(
                "DELETE FROM listings WHERE last_seen<? AND key NOT IN (SELECT listing_key FROM deliveries WHERE status='pending')",
                (time.time() - 30 * 86400,),
            )
            self.db.execute(
                "DELETE FROM pages WHERE updated<?", (time.time() - 7 * 86400,)
            )
