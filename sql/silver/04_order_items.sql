-- SILVER: valid, unique order lines
-- Grain: one row per (order_id, product_id).
DROP TABLE IF EXISTS silver_order_items;
CREATE TABLE silver_order_items AS
WITH ranked AS (
    SELECT b.*,
           ROW_NUMBER() OVER (
               PARTITION BY TRIM(order_id), TRIM(product_id)
               ORDER BY _ingested_at DESC, _source_file DESC
           ) AS rn
    FROM bronze_order_items b
    WHERE order_id IS NOT NULL AND product_id IS NOT NULL
)
SELECT TRIM(order_id)         AS order_id,
       TRIM(product_id)       AS product_id,
       CAST(quantity AS INTEGER) AS quantity,
       CAST(unit_price AS REAL)  AS unit_price
FROM ranked
WHERE rn = 1
  AND CAST(quantity AS INTEGER) > 0
  AND CAST(unit_price AS REAL) > 0
  AND TRIM(order_id)   IN (SELECT order_id FROM silver_orders)
  AND TRIM(product_id) IN (SELECT product_id FROM silver_products);

CREATE UNIQUE INDEX idx_silver_items_pk ON silver_order_items(order_id, product_id);
