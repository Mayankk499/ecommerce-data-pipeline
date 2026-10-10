-- SILVER: valid, unique orders
-- Rules (anything failing goes to silver_rejected with a reason, see 05_rejected.sql):
--   1. duplicate order_id deliveries collapse to the most recently ingested one
--   2. order_ts must parse as a timestamp
--   3. customer must exist in silver_customers
--   4. status (lower-cased) must be one of the known values
DROP TABLE IF EXISTS silver_orders;
CREATE TABLE silver_orders AS
WITH ranked AS (
    SELECT b.*,
           ROW_NUMBER() OVER (
               PARTITION BY TRIM(order_id)
               ORDER BY _ingested_at DESC, _source_file DESC
           ) AS rn
    FROM bronze_orders b
    WHERE order_id IS NOT NULL
)
SELECT TRIM(order_id)             AS order_id,
       TRIM(customer_id)          AS customer_id,
       DATETIME(order_ts)         AS order_ts,
       LOWER(TRIM(status))        AS status,
       LOWER(TRIM(payment_method)) AS payment_method
FROM ranked
WHERE rn = 1
  AND DATETIME(order_ts) IS NOT NULL
  AND TRIM(customer_id) IN (SELECT customer_id FROM silver_customers)
  AND LOWER(TRIM(status)) IN ('completed', 'shipped', 'cancelled', 'returned');

CREATE UNIQUE INDEX idx_silver_orders_pk ON silver_orders(order_id);
