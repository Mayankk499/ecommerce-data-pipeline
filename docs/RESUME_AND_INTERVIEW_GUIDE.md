# Resume & Interview Guide

## 1. Resume entry

**E-commerce Batch Data Pipeline** | Python, SQL, Data Modeling, Airflow-ready, GitHub Actions | [GitHub link]

* Built an end-to-end ELT pipeline (bronze/silver/gold medallion architecture) ingesting 27K+ raw records from CSV and
  JSON files and modelling them into a star schema (3 dimensions, 1 fact table, 4 business marts).
* Implemented **idempotent, incremental ingestion** using file checksums and transactional load logging, so re-runs and
  late-arriving files never create duplicates.
* Wrote 16 automated **data-quality checks** (uniqueness, referential integrity, reconciliation between layers) that fail
  the pipeline on bad data; quarantined ~900 invalid records with rejection reasons instead of dropping them.
* Used advanced SQL (CTEs, window functions, recursive calendar dimension) to produce revenue trends, customer
  segmentation and product rankings.
* Added 13 automated tests, including a hand-verified golden dataset, and a CI workflow (GitHub Actions) that runs tests
  and an end-to-end pipeline run on every commit.

> **Use your own numbers.** Run the project and quote what *you* see. Never claim anything you can't explain: if you
> haven't run the Airflow DAG yourself, don't list "Airflow" as something you used (say "Airflow-ready" or do the
> roadmap exercise first).

Short version (if space is tight, 2 bullets):

* Built a Python + SQL ELT pipeline (bronze/silver/gold, star schema) processing 27K+ records with incremental,
  idempotent loads and 16 automated data-quality checks that gate the marts.
* Quarantined invalid records with reasons, reconciled revenue across layers, and covered logic with 13 tests plus
  GitHub Actions CI.

## 2. 60-second pitch (say this when asked "tell me about this project")

"I built a batch pipeline for an e-commerce company's order data. Files land as CSV and JSON, I load them untouched
into a bronze layer, clean and de-duplicate in silver, then model a star schema in gold for analytics. The part I'm
proudest of is reliability: loads are idempotent using file hashes, bad records go to a quarantine table with a reason,
and 16 quality checks, including reconciliation of revenue between layers, stop the pipeline if something is wrong.
I proved the logic with a small golden dataset where I calculated the expected results by hand."

## 3. Questions you should be ready for (with answer outlines)

1. **Why bronze/silver/gold?** Separation of concerns: bronze = replayable raw truth; silver = trusted clean entities;
   gold = business-shaped. If a rule changes you rebuild silver/gold from bronze without re-fetching the source.
2. **How do you avoid duplicates if the job runs twice?** SHA-256 per file in `ops_load_log` + one transaction for rows
   and log entry; plus `ROW_NUMBER()` dedup in silver for duplicates inside the data itself.
3. **What's the grain of your fact table?** One row per order line (order_id + product). Say why: it lets you aggregate
   to order, customer, product, day without double counting.
4. **Why is cancelled-order revenue excluded?** Business definition encoded as `is_revenue`; rows are kept so you can
   still analyse cancellation rates.
5. **What happens with bad data?** Rejected with a reason into `silver_rejected`; warn vs error severity; error stops
   the pipeline. Mention that you can report rejects back to the source team.
6. **How would this scale to 100x / 1B rows?** Partitioned Parquet in S3/GCS, a columnar engine (Spark, BigQuery,
   Snowflake, DuckDB), incremental merge models per partition instead of full rebuilds, orchestration with Airflow.
7. **How would you make silver incremental?** Process only new bronze partitions, `MERGE`/upsert on the business key,
   keep a high-watermark. (Know the limitation of the current full rebuild and say it openly.)
8. **SCD types?** Customers use type 1 (overwrite, latest wins). Type 2 would keep history with valid_from/valid_to; you
   can describe how you'd extend `gold_dim_customer`.
9. **How do you know the numbers are right?** Golden-dataset tests and reconciliation checks between layers.
10. **Why SQLite?** Zero-install portability for a portfolio project; SQL is standard and I know how to port it
    (DuckDB/Postgres/Snowflake). Don't be defensive; this is an honest, reasonable trade-off.

## 4. Make it truly yours (do at least two before applying)

Recruiters and interviewers can tell a copied project. Small personal changes also make you able to explain every line.

* Replace the synthetic data with a **real public dataset** (e.g. Olist Brazilian e-commerce on Kaggle, NYC taxi trips)
  and adapt the cleaning rules.
* Port the warehouse from SQLite to **DuckDB** or **PostgreSQL** (`docker run postgres`) and write what you changed.
* Run the DAG in **Airflow** locally, take a screenshot of a successful run for the README.
* Build a small **Streamlit / Metabase / Power BI dashboard** on the gold marts; add a screenshot to the README.
* Add one new quality check and one new mart (for example: cancellation rate by payment method).

## 5. Before you publish

- [ ] Public GitHub repo, clean commit history (commit as you build, not one giant commit)
- [ ] CI badge passing; screenshot of `make all` output in the README
- [ ] Your own name in the LICENSE and README, plus a short "What I learned" section
- [ ] You can explain every file without looking at it
