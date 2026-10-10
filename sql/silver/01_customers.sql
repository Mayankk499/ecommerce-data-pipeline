-- SILVER: cleaned, typed, de-duplicated customers
-- * latest record per customer wins (SCD type-1 style)
-- * country standardised through the ref_country_map seed
-- * invalid emails set to NULL instead of dropping the customer
DROP TABLE IF EXISTS silver_customers;
CREATE TABLE silver_customers AS
WITH ranked AS (
    SELECT b.*,
           ROW_NUMBER() OVER (
               PARTITION BY TRIM(customer_id)
               ORDER BY updated_at DESC, _ingested_at DESC
           ) AS rn
    FROM bronze_customers b
    WHERE customer_id IS NOT NULL AND TRIM(customer_id) <> ''
)
SELECT TRIM(r.customer_id)                                   AS customer_id,
       TRIM(r.full_name)                                     AS full_name,
       CASE WHEN r.email LIKE '%_@_%._%' THEN LOWER(TRIM(r.email)) END AS email,
       COALESCE(m.country, 'Unknown')                        AS country,
       DATE(r.signup_date)                                   AS signup_date
FROM ranked r
LEFT JOIN ref_country_map m ON UPPER(TRIM(r.country)) = m.raw_value
WHERE r.rn = 1;

CREATE UNIQUE INDEX idx_silver_customers_pk ON silver_customers(customer_id);
