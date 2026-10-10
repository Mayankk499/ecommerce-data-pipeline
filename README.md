# E-commerce Data Pipeline (Bronze → Silver → Gold)

An end-to-end **batch ELT pipeline** that ingests messy e-commerce source files, cleans and models them
into a **star schema**, enforces **data-quality gates**, and publishes **analytics-ready marts**.

Pure Python standard library + SQL, so it runs anywhere with **zero installs**:

## Architecture

| Layer | Purpose | Tables |
|---|---|---|
| **Bronze** | Exact copy of the source + `_source_file`, `_ingested_at` | `bronze_*` |
| **Silver** | Cleaned, typed, de-duplicated, validated | `silver_*`, `silver_rejected` |
| **Gold** | Star schema + marts for BI | `gold_dim_*`, `gold_fact_sales`, `gold_mart_*` |
| **Ops** | Pipeline metadata | `ops_load_log`, `ops_dq_results` |

| Real-world problem | How it's handled | Where |
|---|---|---|
| Files get re-delivered / pipeline re-run | **Idempotent** loads tracked by SHA-256 in `ops_load_log` | `pipeline/ingest.py` |
| New day of data arrives | **Incremental**: only new/changed files are read | `pipeline/ingest.py` |
| Crash mid-load | Rows + log entry committed in **one transaction** | `pipeline/ingest.py` |
| One corrupt JSON line | Counted in `bad_lines`, file still loads | `pipeline/ingest.py` |
| Duplicate orders / order lines | `ROW_NUMBER()` window de-duplication | `sql/silver/` |
| `"india"`, `"IN "`, `"U.K."` | Standardised via a **seed/reference table** | `seeds/country_map.csv` |
| Customer details change over time | Latest record wins (SCD-1) | `sql/silver/01_customers.sql` |
| Invalid / orphan records | **Quarantined with a reason**, never silently dropped | `sql/silver/05_rejected.sql` |
| Bad data reaching dashboards | 16 SQL **quality checks**; error-level failures exit non-zero | `pipeline/quality.py` |
| "Do the numbers add up?" | **Reconciliation** checks between layers | `pipeline/quality.py` |
| Refactoring breaks logic | **Golden-dataset tests** with hand-computed expectations | `tests/` |

## Quick start

Individual stages: `python3 -m pipeline ingest | transform | quality`.

Try the incremental behaviour:

## Sample results (30 days, default seed)

* 62 files / 27,162 raw rows ingested in under a second
* 7,256 valid orders, 17,865 order lines, 926 rejected records (each with a reason)
* All 16 quality checks pass; the test-suite proves they **fail** when data is corrupted

SQL techniques used: CTEs, window functions (`ROW_NUMBER`, `RANK`, `NTILE`, `LAG`, moving `AVG`),
recursive CTE (calendar dimension), anti-joins, surrogate keys, unique indexes.

## Project layout

## Design decisions & trade-offs

* **SQLite as the warehouse** keeps the project installable anywhere. The SQL is intentionally standard
  (CTEs/window functions) so it ports to **DuckDB, PostgreSQL, BigQuery or Snowflake** with small syntax changes
  (`QUALIFY`, `TRY_CAST`, schemas instead of `bronze_` prefixes). See `docs/ROADMAP.md`.
* **Silver/gold are fully rebuilt each run** (simple and correct at this size). At scale you'd make them
  incremental (merge/upsert by partition) - this is discussed in the interview guide.
* **Quality checks are plain SQL** returning violation counts, so adding one takes a few lines
