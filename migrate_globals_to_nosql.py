#!/usr/bin/env python3
"""One-shot migration: SQLite global databases → NoSQL JSON/JSONL.

Migrates:
  - databases/news_watcher/global_news.db   → JSON via global_news_nosql
  - databases/news_watcher/global_feeds.db  → JSON via global_feeds_nosql
  - databases/shared_poe2/poe2STDpricehistory.db → poe2_nosql (prices)
  - databases/shared_poe2/PoE2Standard.db   → notifications JSON

Behavior:
  - Idempotent: safe to run multiple times.
  - Creates a .bak copy of each .db before reading.
  - Does NOT delete original .db files. Use --rename-deprecated to
    rename them to .db.deprecated_YYYYMMDD after a successful run.

Usage:
  python3 migrate_globals_to_nosql.py [--rename-deprecated] [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def _backup(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None
    bak = db_path.with_suffix(db_path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(db_path, bak)
        print(f"  📦 Backup created: {bak}")
    return bak


def _rename_deprecated(db_path: Path) -> None:
    if not db_path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d")
    target = db_path.with_suffix(db_path.suffix + f".deprecated_{stamp}")
    db_path.rename(target)
    print(f"  🗑️  Renamed: {db_path.name} → {target.name}")


# ---------------------------------------------------------------------------
# Migrators
# ---------------------------------------------------------------------------

def migrate_global_news(dry_run: bool = False) -> int:
    """Migrate global_news.db → global_news_nosql."""
    db_path = BASE / "databases" / "news_watcher" / "global_news.db"
    if not db_path.exists():
        print("  ⚠️  global_news.db not found, skipping")
        return 0
    _backup(db_path)
    if dry_run:
        return 0

    from global_news_nosql import get_global_news_nosql
    nosql = get_global_news_nosql()

    count = 0
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        # global_news table: track which news entries have been seen
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cursor.fetchall()}

        if "global_news" in tables:
            cursor.execute("SELECT * FROM global_news")
            cols = [d[0] for d in cursor.description]
            for row in cursor.fetchall():
                entry = dict(zip(cols, row))
                # mark_processed expects a guid + feed_url
                guid = entry.get("guid") or entry.get("link") or entry.get("id")
                feed_url = entry.get("feed_url") or entry.get("feed") or ""
                if guid and hasattr(nosql, "mark_processed"):
                    try:
                        nosql.mark_processed(str(guid), str(feed_url))
                        count += 1
                    except Exception:
                        pass
    finally:
        conn.close()
    print(f"  ✅ global_news: {count} entries migrated")
    return count


def migrate_global_feeds(dry_run: bool = False) -> int:
    """Migrate global_feeds.db → global_feeds_nosql."""
    db_path = BASE / "databases" / "news_watcher" / "global_feeds.db"
    if not db_path.exists():
        print("  ⚠️  global_feeds.db not found, skipping")
        return 0
    _backup(db_path)
    if dry_run:
        return 0

    from roles.news_watcher.global_feeds_nosql import get_global_feeds_nosql
    nosql = get_global_feeds_nosql()

    count = 0
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM feeds")
        cols = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            entry = dict(zip(cols, row))
            try:
                nosql.add_feed(
                    feed_id=entry.get("id") or entry.get("feed_id"),
                    name=entry.get("name", ""),
                    url=entry.get("url", ""),
                    category=entry.get("category", ""),
                    language=entry.get("language", "en"),
                )
                if entry.get("status"):
                    nosql.update_feed_status(entry["id"], entry["status"], entry.get("error_message"))
                count += 1
            except Exception as e:
                print(f"    ⚠️  feed migration error: {e}")
    finally:
        conn.close()
    print(f"  ✅ global_feeds: {count} feeds migrated")
    return count


def migrate_poe2_prices(dry_run: bool = False) -> int:
    """Migrate poe2STDpricehistory.db → poe2_nosql (per-league)."""
    db_path = BASE / "databases" / "shared_poe2" / "poe2STDpricehistory.db"
    if not db_path.exists():
        print("  ⚠️  poe2STDpricehistory.db not found, skipping")
        return 0
    _backup(db_path)
    if dry_run:
        return 0

    from roles.treasure_hunter.poe2.poe2_nosql import get_poe2_nosql
    nosql = get_poe2_nosql()

    count = 0
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        # Read items_registry to know item_id -> name + league
        cursor.execute("SELECT item_id, item_name, league FROM items_registry")
        items = cursor.fetchall()

        for item_id, item_name, league in items:
            nosql.save_item(item_name, {"item_id": item_id, "name": item_name, "league": league})
            tbl = f"prices_item_{item_id}"
            try:
                cursor.execute(f"SELECT * FROM {tbl}")
                cols = [d[0] for d in cursor.description]
                for row in cursor.fetchall():
                    entry = dict(zip(cols, row))
                    entry["item_id"] = item_id
                    nosql.append_price_history(entry, league)
                    # Also save as latest price
                    if "price" in entry or "value" in entry:
                        price_val = entry.get("price") or entry.get("value")
                        ts = entry.get("timestamp") or entry.get("created_at") or ""
                        nosql.save_latest_price(league, item_id, {"price": price_val, "updated_at": ts})
                    count += 1
            except sqlite3.OperationalError:
                continue
    finally:
        conn.close()
    print(f"  ✅ POE2 prices: {count} entries migrated across {len(items)} items")
    return count


def migrate_poe2_standard(dry_run: bool = False) -> int:
    """Migrate PoE2Standard.db (notifications) → JSON."""
    db_path = BASE / "databases" / "shared_poe2" / "PoE2Standard.db"
    if not db_path.exists():
        print("  ⚠️  PoE2Standard.db not found, skipping")
        return 0
    _backup(db_path)
    if dry_run:
        return 0

    import json
    out = BASE / "databases" / "shared" / "poe2" / "notifications.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cursor.fetchall()}
        records = []
        if "notificaciones" in tables:
            cursor.execute("SELECT * FROM notificaciones")
            cols = [d[0] for d in cursor.description]
            for row in cursor.fetchall():
                records.append(dict(zip(cols, row)))
                count += 1
        out.write_text(json.dumps({"notifications": records}, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        conn.close()
    print(f"  ✅ POE2Standard notifications: {count} entries → {out}")
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate global SQLite DBs → NoSQL")
    parser.add_argument("--dry-run", action="store_true", help="Backup only, no writes")
    parser.add_argument("--rename-deprecated", action="store_true",
                        help="After successful migration, rename .db files to .db.deprecated_YYYYMMDD")
    args = parser.parse_args()

    print("🚀 Starting global SQLite → NoSQL migration")
    if args.dry_run:
        print("ℹ️  DRY RUN: backups only, no NoSQL writes")

    print("\n[1/4] Migrating global_news.db ...")
    migrate_global_news(args.dry_run)

    print("\n[2/4] Migrating global_feeds.db ...")
    migrate_global_feeds(args.dry_run)

    print("\n[3/4] Migrating poe2STDpricehistory.db ...")
    migrate_poe2_prices(args.dry_run)

    print("\n[4/4] Migrating PoE2Standard.db ...")
    migrate_poe2_standard(args.dry_run)

    if args.rename_deprecated and not args.dry_run:
        print("\n🗑️  Renaming legacy .db files to .deprecated_<date>")
        for p in [
            BASE / "databases" / "news_watcher" / "global_news.db",
            BASE / "databases" / "news_watcher" / "global_feeds.db",
            BASE / "databases" / "shared_poe2" / "poe2STDpricehistory.db",
            BASE / "databases" / "shared_poe2" / "PoE2Standard.db",
        ]:
            _rename_deprecated(p)

    print("\n✅ Migration complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
