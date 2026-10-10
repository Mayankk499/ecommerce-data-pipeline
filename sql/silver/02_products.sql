-- SILVER: products (typed, de-duplicated)
DROP TABLE IF EXISTS silver_products;
CREATE TABLE silver_products AS
WITH ranked AS (
    SELECT b.*,
           ROW_NUMBER() OVER (PARTITION BY TRIM(product_id) ORDER BY _ingested_at DESC) AS rn
    FROM bronze_products b
    WHERE product_id IS NOT NULL AND TRIM(product_id) <> ''
)
SELECT TRIM(product_id)                AS product_id,
       TRIM(product_name)              AS product_name,
       COALESCE(TRIM(category), 'Other') AS category,
       CAST(list_price AS REAL)        AS list_price
FROM ranked
WHERE rn = 1;

CREATE UNIQUE INDEX idx_silver_products_pk ON silver_products(product_id);
