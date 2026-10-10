"""Tests. Run with:  python -m unittest discover -s tests -v   (or `pytest` if installed)

Two styles of test:
  1. GOLDEN dataset - tiny hand-written input where every expected number is
     known in advance (best way to prove transformation logic is correct).
  2. PROPERTY / behaviour tests on generated data - idempotency, incremental
     loads, and "do the data-quality checks actually catch bad data?".
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.db import connect, scalar  # noqa: E402
from pipeline.generate_data import generate  # noqa: E402
from pipeline.ingest import ingest  # noqa: E402
from pipeline.quality import has_failures, run_checks  # noqa: E402
from pipeline.transform import transform  # noqa: E402


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def build_golden(raw: Path) -> None:
    write(raw / "customers.csv",
          "customer_id,full_name,email,country,signup_date,updated_at\n"
          "C1,Asha,ASHA@Example.com,india,2025-12-01,2026-01-01T09:00:00\n"
          "C1,Asha,ASHA@Example.com,uk,2025-12-01,2026-01-02T09:00:00\n"   # later update wins
          "C2,Bob,not-an-email,usa,2025-12-05,2026-01-01T09:00:00\n")
    write(raw / "products.csv",
          "product_id,product_name,category,list_price\nP1,Pen,Books,10.00\nP2,Lamp,Home,20.00\n")
    orders = [
        {"order_id": "O1", "customer_id": "C1", "order_ts": "2026-01-01T10:00:00", "status": "completed", "payment_method": "card"},
        {"order_id": "O1", "customer_id": "C1", "order_ts": "2026-01-01T10:00:00", "status": "completed", "payment_method": "card"},  # duplicate
        {"order_id": "O2", "customer_id": "C2", "order_ts": "2026-01-01T11:00:00", "status": "COMPLETED", "payment_method": "upi"},
        {"order_id": "O3", "customer_id": "C99", "order_ts": "2026-01-01T12:00:00", "status": "completed", "payment_method": "card"},  # orphan
        {"order_id": "O4", "customer_id": "C1", "order_ts": "2026-01-01T13:00:00", "status": "cancelled", "payment_method": "card"},
        {"order_id": "O5", "customer_id": "C1", "order_ts": "not-a-date", "status": "completed", "payment_method": "card"},       # bad ts
    ]
    write(raw / "orders" / "orders_2026-01-01.jsonl", "\n".join(json.dumps(o) for o in orders) + "\n")
    write(raw / "order_items" / "order_items_2026-01-01.csv",
          "order_id,product_id,quantity,unit_price\n"
          "O1,P1,2,10.00\nO1,P1,2,10.00\nO1,P2,1,20.00\n"   # O1 = 40 (duplicate line removed)
          "O2,P2,3,20.00\nO2,P1,-1,10.00\n"                 # O2 = 60, negative qty rejected
          "O3,P1,1,10.00\n"                                  # parent order rejected
          "O4,P1,1,10.00\n")                                 # cancelled -> not revenue


class GoldenDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        raw = Path(cls.tmp.name) / "raw"
        build_golden(raw)
        cls.conn = connect(Path(cls.tmp.name) / "wh.db")
        ingest(cls.conn, raw)
        transform(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.tmp.cleanup()

    def q(self, sql):
        return scalar(self.conn, sql)

    def test_duplicates_removed_and_bad_rows_rejected(self):
        self.assertEqual(self.q("SELECT COUNT(*) FROM silver_orders"), 3)        # O1, O2, O4
        self.assertEqual(self.q("SELECT COUNT(*) FROM silver_order_items"), 4)   # O1xP1, O1xP2, O2xP2, O4xP1

    def test_rejected_reasons(self):
        rows = {(r["source_table"], r["record_key"], r["reason"])
                for r in self.conn.execute("SELECT * FROM silver_rejected")}
        self.assertEqual(rows, {
            ("orders", "O3", "unknown_customer"),
            ("orders", "O5", "invalid_order_ts"),
            ("order_items", "O3|P1", "order_missing_or_rejected"),
            ("order_items", "O2|P1", "invalid_quantity"),
        })

    def test_latest_customer_record_wins_and_country_standardised(self):
        self.assertEqual(self.q("SELECT country FROM silver_customers WHERE customer_id='C1'"), "United Kingdom")
        self.assertEqual(self.q("SELECT country FROM silver_customers WHERE customer_id='C2'"), "United States")

    def test_email_cleaning(self):
        self.assertEqual(self.q("SELECT email FROM silver_customers WHERE customer_id='C1'"), "asha@example.com")
        self.assertIsNone(self.q("SELECT email FROM silver_customers WHERE customer_id='C2'"))

    def test_revenue_numbers_are_exact(self):
        self.assertEqual(self.q("SELECT SUM(line_amount) FROM gold_fact_sales WHERE is_revenue=1"), 100.0)
        self.assertEqual(self.q("SELECT revenue FROM gold_mart_daily_revenue WHERE date='2026-01-01'"), 100.0)
        self.assertEqual(self.q("SELECT orders FROM gold_mart_daily_revenue WHERE date='2026-01-01'"), 2)

    def test_cancelled_order_kept_but_not_revenue(self):
        self.assertEqual(self.q("SELECT is_revenue FROM gold_fact_sales WHERE order_id='O4'"), 0)

    def test_all_quality_checks_pass(self):
        results = run_checks(self.conn)
        self.assertFalse(has_failures(results), [r for r in results if r["status"] == "FAIL"])


class BehaviourTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "raw"
        generate(self.raw, days=5, orders_per_day=40, customers=100)
        self.conn = connect(Path(self.tmp.name) / "wh.db")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_ingest_is_idempotent(self):
        first = ingest(self.conn, self.raw)
        counts = [scalar(self.conn, f"SELECT COUNT(*) FROM {t}") for t in
                  ("bronze_orders", "bronze_order_items", "bronze_customers")]
        second = ingest(self.conn, self.raw)
        counts_after = [scalar(self.conn, f"SELECT COUNT(*) FROM {t}") for t in
                        ("bronze_orders", "bronze_order_items", "bronze_customers")]
        self.assertGreater(first["files_loaded"], 0)
        self.assertEqual(second["files_loaded"], 0)
        self.assertEqual(counts, counts_after)

    def test_incremental_load_only_reads_new_files(self):
        ingest(self.conn, self.raw)
        generate(self.raw, days=7, orders_per_day=40, customers=100)  # 2 extra days
        summary = ingest(self.conn, self.raw)
        self.assertEqual(summary["files_loaded"], 4)  # 2 days x (orders + items)

    def test_full_pipeline_passes_quality_on_generated_data(self):
        ingest(self.conn, self.raw)
        transform(self.conn)
        results = run_checks(self.conn)
        self.assertFalse(has_failures(results), [r for r in results if r["status"] == "FAIL"])
        self.assertGreater(scalar(self.conn, "SELECT COUNT(*) FROM silver_rejected"), 0)

    def test_transform_is_repeatable(self):
        ingest(self.conn, self.raw)
        transform(self.conn)
        a = scalar(self.conn, "SELECT ROUND(SUM(revenue), 2) FROM gold_mart_daily_revenue")
        transform(self.conn)
        b = scalar(self.conn, "SELECT ROUND(SUM(revenue), 2) FROM gold_mart_daily_revenue")
        self.assertEqual(a, b)

    def test_quality_checks_catch_corrupted_data(self):
        """A test for the tests: break the warehouse on purpose and expect FAIL."""
        ingest(self.conn, self.raw)
        transform(self.conn)
        self.conn.execute("UPDATE gold_fact_sales SET quantity = -5 WHERE rowid = 1")
        self.conn.execute("DELETE FROM gold_dim_product WHERE product_key = 1")
        self.conn.commit()
        failed = {r["check"] for r in run_checks(self.conn) if r["status"] == "FAIL"}
        self.assertIn("quantity and amounts are positive", failed)
        self.assertIn("fact -> dim_product integrity", failed)

    def test_malformed_json_line_does_not_crash_ingest(self):
        bad = self.raw / "orders" / "orders_2026-02-01.jsonl"
        write(bad, '{"order_id": "OX1", "customer_id": "C00001", "order_ts": "2026-02-01T10:00:00", '
                   '"status": "completed", "payment_method": "card"}\n{this is not json\n')
        ingest(self.conn, self.raw)
        self.assertEqual(scalar(self.conn, "SELECT bad_lines FROM ops_load_log WHERE file_path LIKE '%2026-02-01%'"), 1)


if __name__ == "__main__":
    unittest.main()
