-- QUARANTINE: every record that failed a silver rule, with the reason.
-- Bad data is never silently dropped - it is stored so it can be inspected,
-- reported to the source team, and replayed after a fix.
DROP TABLE IF EXISTS silver_rejected;
CREATE TABLE silver_rejected AS
WITH orders_dedup AS (
    SELECT b.*,
           ROW_NUMBER() OVER (
               PARTITION BY TRIM(order_id) ORDER BY _ingested_at DESC, _source_file DESC
           ) AS rn
    FROM bronze_orders b
    WHERE order_id IS NOT NULL
),
items_dedup AS (
    SELECT b.*,
           ROW_NUMBER() OVER (
               PARTITION BY TRIM(order_id), TRIM(product_id)
               ORDER BY _ingested_at DESC, _source_file DESC
           ) AS rn
    FROM bronze_order_items b
    WHERE order_id IS NOT NULL AND product_id IS NOT NULL
)
SELECT 'orders' AS source_table,
       TRIM(order_id) AS record_key,
       _source_file,
       CASE
           WHEN DATETIME(order_ts) IS NULL THEN 'invalid_order_ts'
           WHEN TRIM(customer_id) NOT IN (SELECT customer_id FROM silver_customers) OR customer_id IS NULL
                THEN 'unknown_customer'
           ELSE 'invalid_status'
       END AS reason
FROM orders_dedup
WHERE rn = 1
  AND TRIM(order_id) NOT IN (SELECT order_id FROM silver_orders)

UNION ALL

SELECT 'order_items',
       TRIM(order_id) || '|' || TRIM(product_id),
       _source_file,
       CASE
           WHEN CAST(quantity AS INTEGER) <= 0 OR quantity IS NULL THEN 'invalid_quantity'
           WHEN CAST(unit_price AS REAL) <= 0 OR unit_price IS NULL THEN 'invalid_price'
           WHEN TRIM(order_id) NOT IN (SELECT order_id FROM silver_orders) THEN 'order_missing_or_rejected'
           ELSE 'unknown_product'
       END
FROM items_dedup
WHERE rn = 1
  AND NOT EXISTS (
      SELECT 1 FROM silver_order_items s
      WHERE s.order_id = TRIM(items_dedup.order_id) AND s.product_id = TRIM(items_dedup.product_id)
  );
