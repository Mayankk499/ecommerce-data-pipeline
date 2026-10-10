"""Command line entry point:  python -m pipeline <command>

Commands
    generate    create messy sample source data
    ingest      raw files -> bronze (incremental, idempotent)
    transform   bronze -> silver -> gold
    quality     run data-quality checks (non-zero exit code on failure)
    run         ingest + transform + quality  (what the scheduler calls)
    report      print business insights from the gold marts
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date

from . import generate_data
from .config import DEFAULT_DB, DEFAULT_RAW_DIR
from .db import connect
from .ingest import ingest
from .quality import has_failures, run_checks
from .transform import transform


def _print_dq(results) -> None:
    print("\nData quality checks")
    print("-" * 78)
    for r in results:
        icon = {"pass": "PASS", "warn": "WARN", "FAIL": "FAIL"}[r["status"]]
        print(f"  [{icon}] {r['check']:<62} violations={r['violations']}")
    print("-" * 78)


def cmd_run(args) -> int:
    t0 = time.perf_counter()
    conn = connect(args.db)
    print(f"1/3 Ingest    {ingest(conn, args.raw_dir)}")
    summary = transform(conn)
    timings = summary.pop("timings_s")
    print(f"2/3 Transform {summary}")
    results = run_checks(conn)
    print("3/3 Quality   done")
    _print_dq(results)
    print(f"Finished in {time.perf_counter() - t0:.1f}s")
    if has_failures(results):
        print("Pipeline FAILED: at least one error-level data quality check did not pass.")
        return 1
    return 0


def cmd_report(args) -> int:
    conn = connect(args.db)

    def show(title, sql):
        print(f"\n{title}")
        rows = conn.execute(sql).fetchall()
        if not rows:
            print("  (no rows)")
            return
        cols = rows[0].keys()
        print("  " + " | ".join(f"{c:<16}" for c in cols))
        for r in rows:
            print("  " + " | ".join(f"{str(r[c]):<16}" for c in cols))

    show("Last 7 days of revenue",
         "SELECT * FROM (SELECT * FROM gold_mart_daily_revenue ORDER BY date DESC LIMIT 7) ORDER BY date")
    show("Top 5 products by revenue",
         "SELECT product_name, category, units_sold, revenue FROM gold_mart_product_performance "
         "ORDER BY revenue DESC LIMIT 5")
    show("Customer segments",
         "SELECT segment, COUNT(*) AS customers, ROUND(SUM(revenue),2) AS revenue, "
         "ROUND(AVG(orders),1) AS avg_orders FROM gold_mart_customer_value GROUP BY segment ORDER BY revenue DESC")
    show("Rejected records by reason",
         "SELECT source_table, reason, COUNT(*) AS records FROM silver_rejected "
         "GROUP BY source_table, reason ORDER BY records DESC")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB), help="warehouse file")
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR), help="raw landing folder")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate sample source data")
    g.add_argument("--days", type=int, default=30)
    g.add_argument("--orders-per-day", type=int, default=200)
    g.add_argument("--start-date", default="2026-01-01")
    g.add_argument("--seed", type=int, default=42)
    for name in ("ingest", "transform", "quality", "run", "report"):
        sub.add_parser(name)

    args = ap.parse_args(argv)
    if args.cmd == "generate":
        generate_data.generate(args.raw_dir, args.days, args.orders_per_day,
                               start=date.fromisoformat(args.start_date), seed=args.seed)
        print(f"Generated {args.days} days of raw data in {args.raw_dir}")
        return 0
    if args.cmd == "ingest":
        print(ingest(connect(args.db), args.raw_dir))
        return 0
    if args.cmd == "transform":
        s = transform(connect(args.db))
        print({k: v for k, v in s.items() if k != "timings_s"})
        return 0
    if args.cmd == "quality":
        res = run_checks(connect(args.db))
        _print_dq(res)
        return 1 if has_failures(res) else 0
    if args.cmd == "run":
        return cmd_run(args)
    return cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
