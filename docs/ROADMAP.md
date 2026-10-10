# Roadmap: levelling the project up

Each step is a self-contained learning exercise and adds a keyword hiring managers search for.

| Step | What to do | Skill it proves |
|---|---|---|
| 1 | Swap SQLite for **DuckDB** (`pip install duckdb`): use real schemas (`bronze.orders`), `QUALIFY`, `TRY_CAST`, read Parquet directly | Modern analytics engines |
| 2 | Write silver output as **Parquet** partitioned by date | Columnar formats, partitioning |
| 3 | Run `dags/ecommerce_pipeline_dag.py` in **Airflow**; add retries and a failure email/Slack alert | Orchestration |
| 4 | Port SQL models to **dbt** (`dbt-duckdb`), use `dbt test` for the quality checks | Analytics engineering |
| 5 | Make silver **incremental** (process only new partitions, upsert by key) | Scalable design |
| 6 | **Dockerise** (`Dockerfile` + `docker-compose` with Postgres + Airflow) | Containers, reproducibility |
| 7 | Land files in **S3 / GCS** (free tier) and load into **BigQuery/Snowflake trial** | Cloud |
| 8 | Add a **Streamlit/Metabase dashboard** on the gold marts | End-to-end delivery |
| 9 | Add **SCD Type 2** to `gold_dim_customer` | Dimensional modelling depth |
| 10 | Add a streaming variant (Kafka + a small consumer) as a separate repo | Streaming basics |
