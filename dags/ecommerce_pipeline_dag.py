"""Apache Airflow DAG that schedules the pipeline daily.

NOTE: this file was written to Airflow 2.x conventions but has NOT been run in
this repo's test environment (Airflow isn't a dependency). To try it:
    pip install apache-airflow
    export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/dags
    airflow standalone
Treat getting it running locally as a learning exercise (see docs/ROADMAP.md).
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "{{ var.value.get('pipeline_dir', '/opt/ecommerce-data-pipeline') }}"

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="ecommerce_daily_pipeline",
    description="raw files -> bronze -> silver -> gold, with data-quality gate",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args=default_args,
    tags=["portfolio", "elt"],
) as dag:
    ingest = BashOperator(task_id="ingest_bronze",
                          bash_command=f"cd {PROJECT_DIR} && python -m pipeline ingest")
    transform = BashOperator(task_id="transform_silver_gold",
                             bash_command=f"cd {PROJECT_DIR} && python -m pipeline transform")
    # non-zero exit code on error-level failures => task fails => downstream/alerts trigger
    quality = BashOperator(task_id="data_quality_gate",
                           bash_command=f"cd {PROJECT_DIR} && python -m pipeline quality")

    ingest >> transform >> quality
