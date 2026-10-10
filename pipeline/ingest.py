"""Bronze layer: land raw files into the warehouse *as-is* (all TEXT).

Design points worth explaining in an interview:

* **Idempotent & incremental** - every file is recorded in `ops_load_log` with
  its SHA-256. Re-running only loads new or changed files.
* **Atomic per file** - rows and the log entry are committed in one
  transaction, so a crash never leaves a half-loaded file marked as done.
* **Raw & lineage-friendly** - nothing is cleaned here. Each row keeps
  `_source_file` and `_ingested_at` so any value can be traced back.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import SEEDS_DIR

BRONZE = {
    "bronze_customers": ["customer_id", "full_name", "email", "country", "signup_date", "updated_at"],
    "bronze_products": ["product_id", "product_name", "category", "list_price"],
    "bronze_orders": ["order_id", "customer_id", "order_ts", "status", "payment_method"],
    "bronze_order_items": ["order_id", "product_id", "quantity", "unit_price"],
}

# (table, glob pattern relative to raw dir, file format)
SOURCES = [
    ("bronze_customers", "customers*.csv", "csv"),
    ("bronze_products", "products*.csv", "csv"),
    ("bronze_orders", "orders/orders_*.jsonl", "jsonl"),
    ("bronze_order_items", "order_items/order_items_*.csv", "csv"),
]


def init_bronze(conn: sqlite3.Connection) -> None:
    for table, cols in BRONZE.items():
        col_sql = ", ".join(f"{c} TEXT" for c in cols)
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table} ({col_sql}, _source_file TEXT, _ingested_at TEXT)"
        )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ops_load_log (
               file_path TEXT, sha256 TEXT, table_name TEXT, row_count INTEGER,
               bad_lines INTEGER, loaded_at TEXT, PRIMARY KEY (file_path, sha256))"""
    )
    conn.commit()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean(v):
    """Raw layer keeps values as text; empty strings become NULL."""
    if v is None:
        return None
    v = str(v)
    return v if v.strip() != "" else None


def _read_csv(path: Path, cols: list[str]):
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            yield tuple(_clean(row.get(c)) for c in cols)


def _read_jsonl(path: Path, cols: list[str], stats: dict):
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                stats["bad_lines"] += 1  # don't fail the whole file for one bad line
                continue
            yield tuple(_clean(rec.get(c)) for c in cols)


def _load_file(conn, table: str, path: Path, fmt: str, raw_dir: Path) -> int | None:
    sha = _sha256(path)
    rel = path.relative_to(raw_dir).as_posix()
    if conn.execute("SELECT 1 FROM ops_load_log WHERE file_path=? AND sha256=?", (rel, sha)).fetchone():
        return None  # already loaded -> skip (idempotency)

    cols = BRONZE[table]
    stats = {"bad_lines": 0}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    reader = _read_csv(path, cols) if fmt == "csv" else _read_jsonl(path, cols, stats)
    rows = [r + (rel, now) for r in reader]
    placeholders = ", ".join("?" * (len(cols) + 2))
    with conn:  # one transaction: data + log entry succeed or fail together
        conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
        conn.execute(
            "INSERT INTO ops_load_log VALUES (?,?,?,?,?,?)",
            (rel, sha, table, len(rows), stats["bad_lines"], now),
        )
    return len(rows)


def load_seeds(conn: sqlite3.Connection, seeds_dir: Path = SEEDS_DIR) -> None:
    """Small reference tables (like dbt seeds): full refresh every run."""
    for csv_path in sorted(Path(seeds_dir).glob("*.csv")):
        table = f"ref_{csv_path.stem}"
        with csv_path.open(newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
        with conn:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.execute(f"CREATE TABLE {table} ({', '.join(h + ' TEXT' for h in header)})")
            conn.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(header))})", rows)


def ingest(conn: sqlite3.Connection, raw_dir) -> dict:
    raw_dir = Path(raw_dir)
    init_bronze(conn)
    load_seeds(conn)
    summary = {"files_loaded": 0, "files_skipped": 0, "rows_loaded": 0}
    for table, pattern, fmt in SOURCES:
        for path in sorted(raw_dir.glob(pattern)):
            n = _load_file(conn, table, path, fmt, raw_dir)
            if n is None:
                summary["files_skipped"] += 1
            else:
                summary["files_loaded"] += 1
                summary["rows_loaded"] += n
    return summary
