-- GOLD: star-schema dimensions with surrogate keys
DROP TABLE IF EXISTS gold_dim_customer;
CREATE TABLE gold_dim_customer AS
SELECT ROW_NUMBER() OVER (ORDER BY customer_id) AS customer_key,
       customer_id, full_name, email, country, signup_date
FROM silver_customers;
CREATE UNIQUE INDEX idx_dim_customer_key ON gold_dim_customer(customer_key);
CREATE UNIQUE INDEX idx_dim_customer_id  ON gold_dim_customer(customer_id);

DROP TABLE IF EXISTS gold_dim_product;
CREATE TABLE gold_dim_product AS
SELECT ROW_NUMBER() OVER (ORDER BY product_id) AS product_key,
       product_id, product_name, category, list_price
FROM silver_products;
CREATE UNIQUE INDEX idx_dim_product_key ON gold_dim_product(product_key);
CREATE UNIQUE INDEX idx_dim_product_id  ON gold_dim_product(product_id);

-- Calendar dimension generated with a recursive CTE covering all order dates
DROP TABLE IF EXISTS gold_dim_date;
CREATE TABLE gold_dim_date AS
WITH RECURSIVE bounds AS (
    SELECT DATE(MIN(order_ts)) AS d0, DATE(MAX(order_ts)) AS d1 FROM silver_orders
),
cal(d) AS (
    SELECT d0 FROM bounds
    UNION ALL
    SELECT DATE(d, '+1 day') FROM cal, bounds WHERE d < d1
)
SELECT CAST(STRFTIME('%Y%m%d', d) AS INTEGER) AS date_key,
       d                                       AS date,
       CAST(STRFTIME('%Y', d) AS INTEGER)      AS year,
       CAST(STRFTIME('%m', d) AS INTEGER)      AS month,
       STRFTIME('%Y-%m', d)                    AS year_month,
       CAST(STRFTIME('%w', d) AS INTEGER)      AS day_of_week,   -- 0 = Sunday
       CASE WHEN STRFTIME('%w', d) IN ('0', '6') THEN 1 ELSE 0 END AS is_weekend
FROM cal;
CREATE UNIQUE INDEX idx_dim_date_key ON gold_dim_date(date_key);
