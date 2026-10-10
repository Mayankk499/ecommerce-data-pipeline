"""Data-quality checks.

Every check is a SQL query that returns the NUMBER OF VIOLATIONS (0 = pass).
Severity:
    error -> pipeline fails (bad data must not reach the marts)
    warn  -> logged, pipeline continues (something worth a human look)
Results are persisted in `ops_dq_results` so quality can be tracked over time.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .db import scalar


@dataclass(frozen=True)
class Check:
    name: str
    severity: str  # "error" | "warn"
    sql: str


CHECKS = [
    # --- uniqueness / primary keys ---------------------------------------
    Check("silver_customers.customer_id is unique", "error",
          "SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM silver_customers"),
    Check("silver_orders.order_id is unique", "error",
          "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM silver_orders"),
    Check("gold_fact_sales grain (order_id, product_key) is unique", "error",
          "SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT order_id, product_key FROM gold_fact_sales)) "
          "FROM gold_fact_sales"),
    # --- not null ---------------------------------------------------------
    Check("gold_fact_sales keys are not null", "error",
          "SELECT COUNT(*) FROM gold_fact_sales "
          "WHERE order_id IS NULL OR customer_key IS NULL OR product_key IS NULL OR date_key IS NULL"),
    # --- referential integrity -------------------------------------------
    Check("fact -> dim_customer integrity", "error",
          "SELECT COUNT(*) FROM gold_fact_sales f "
          "LEFT JOIN gold_dim_customer d USING (customer_key) WHERE d.customer_key IS NULL"),
    Check("fact -> dim_product integrity", "error",
          "SELECT COUNT(*) FROM gold_fact_sales f "
          "LEFT JOIN gold_dim_product d USING (product_key) WHERE d.product_key IS NULL"),
    Check("fact -> dim_date integrity", "error",
          "SELECT COUNT(*) FROM gold_fact_sales f "
          "LEFT JOIN gold_dim_date d USING (date_key) WHERE d.date_key IS NULL"),
    # --- accepted values / ranges ----------------------------------------
    Check("order status in accepted values", "error",
          "SELECT COUNT(*) FROM silver_orders "
          "WHERE status NOT IN ('completed','shipped','cancelled','returned')"),
    Check("quantity and amounts are positive", "error",
          "SELECT COUNT(*) FROM gold_fact_sales WHERE quantity <= 0 OR unit_price <= 0 OR line_amount <= 0"),
    Check("no order timestamps in the future", "error",
          "SELECT COUNT(*) FROM silver_orders WHERE order_ts > DATETIME('now')"),
    # --- reconciliation (do the layers agree with each other?) -----------
    Check("fact revenue reconciles with silver order items", "error",
          "SELECT CASE WHEN ABS((SELECT SUM(line_amount) FROM gold_fact_sales) - "
          "(SELECT SUM(quantity * unit_price) FROM silver_order_items)) > 0.01 THEN 1 ELSE 0 END"),
    Check("daily revenue mart reconciles with fact", "error",
          "SELECT CASE WHEN ABS((SELECT SUM(revenue) FROM gold_mart_daily_revenue) - "
          "(SELECT SUM(line_amount) FROM gold_fact_sales WHERE is_revenue = 1)) > 0.01 THEN 1 ELSE 0 END"),
    Check("no silver order lost between silver and fact (orders with items)", "error",
          "SELECT COUNT(DISTINCT order_id) - (SELECT COUNT(DISTINCT order_id) FROM gold_fact_sales) "
          "FROM silver_order_items"),
    # --- volume / drift warnings -----------------------------------------
    Check("rejected records < 5% of bronze rows", "warn",
          "SELECT CASE WHEN 1.0 * (SELECT COUNT(*) FROM silver_rejected) / "
          "((SELECT COUNT(*) FROM bronze_orders) + (SELECT COUNT(*) FROM bronze_order_items)) > 0.05 "
          "THEN 1 ELSE 0 END"),
    Check("customers with missing email < 10%", "warn",
          "SELECT CASE WHEN 1.0 * SUM(email IS NULL) / COUNT(*) > 0.10 THEN 1 ELSE 0 END FROM silver_customers"),
    Check("daily revenue mart is not empty", "error",
          "SELECT CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END FROM gold_mart_daily_revenue"),
]


def run_checks(conn: sqlite3.Connection) -> list[dict]:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ops_dq_results (
               run_id TEXT, check_name TEXT, severity TEXT,
               violations INTEGER, status TEXT, checked_at TEXT)"""
    )
    run_id = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []
    for chk in CHECKS:
        violations = scalar(conn, chk.sql) or 0
        status = "pass" if violations == 0 else ("FAIL" if chk.severity == "error" else "warn")
        results.append({"run_id": run_id, "check": chk.name, "severity": chk.severity,
                        "violations": violations, "status": status})
    with conn:
        conn.executemany(
            "INSERT INTO ops_dq_results VALUES (?,?,?,?,?,?)",
            [(r["run_id"], r["check"], r["severity"], r["violations"], r["status"], now) for r in results],
        )
    return results


def has_failures(results: list[dict]) -> bool:
    return any(r["status"] == "FAIL" for r in results)
