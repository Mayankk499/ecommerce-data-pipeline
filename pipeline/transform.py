"""Run the SQL transformation layers in order: silver -> gold.

SQL lives in plain .sql files (numbered for execution order) instead of being
buried in Python strings - the same idea as dbt models, without the tooling.
Each layer is rebuilt from the layer below, so the whole warehouse can always
be recreated from bronze (and bronze from the raw files).
"""
from __future__ import annotations

import sqlite3
import time

from .config import SQL_DIR
from .db import run_sql_file, scalar


def transform(conn: sqlite3.Connection) -> dict:
    timings = {}
    for layer in ("silver", "gold"):
        for path in sorted((SQL_DIR / layer).glob("*.sql")):
            t0 = time.perf_counter()
            run_sql_file(conn, path)
            timings[f"{layer}/{path.name}"] = round(time.perf_counter() - t0, 3)
    conn.commit()
    return {
        "silver_orders": scalar(conn, "SELECT COUNT(*) FROM silver_orders"),
        "silver_order_items": scalar(conn, "SELECT COUNT(*) FROM silver_order_items"),
        "rejected": scalar(conn, "SELECT COUNT(*) FROM silver_rejected"),
        "fact_rows": scalar(conn, "SELECT COUNT(*) FROM gold_fact_sales"),
        "timings_s": timings,
    }
