-- GOLD: business-facing marts (what a dashboard / analyst queries)

-- 1) Daily revenue with 7-day moving average and day-over-day change (window functions)
DROP TABLE IF EXISTS gold_mart_daily_revenue;
CREATE TABLE gold_mart_daily_revenue AS
WITH daily AS (
    SELECT d.date,
           COUNT(DISTINCT f.order_id)      AS orders,
           SUM(f.quantity)                 AS units,
           ROUND(SUM(f.line_amount), 2)    AS revenue
    FROM gold_fact_sales f
    JOIN gold_dim_date d ON d.date_key = f.date_key
    WHERE f.is_revenue = 1
    GROUP BY d.date
)
SELECT date, orders, units, revenue,
       ROUND(revenue * 1.0 / orders, 2) AS avg_order_value,
       ROUND(AVG(revenue) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS revenue_7d_avg,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY date))
             / NULLIF(LAG(revenue) OVER (ORDER BY date), 0), 1) AS revenue_dod_pct
FROM daily;

-- 2) Product performance, ranked inside each category
DROP TABLE IF EXISTS gold_mart_product_performance;
CREATE TABLE gold_mart_product_performance AS
WITH agg AS (
    SELECT p.product_id, p.product_name, p.category,
           SUM(f.quantity)              AS units_sold,
           ROUND(SUM(f.line_amount), 2) AS revenue
    FROM gold_fact_sales f
    JOIN gold_dim_product p ON p.product_key = f.product_key
    WHERE f.is_revenue = 1
    GROUP BY p.product_id, p.product_name, p.category
)
SELECT *, RANK() OVER (PARTITION BY category ORDER BY revenue DESC) AS rank_in_category
FROM agg;

-- 3) Customer value: recency / frequency / monetary + quartile segment
DROP TABLE IF EXISTS gold_mart_customer_value;
CREATE TABLE gold_mart_customer_value AS
WITH agg AS (
    SELECT c.customer_id, c.country,
           COUNT(DISTINCT f.order_id)   AS orders,
           ROUND(SUM(f.line_amount), 2) AS revenue,
           DATE(MIN(f.order_ts))        AS first_order_date,
           DATE(MAX(f.order_ts))        AS last_order_date
    FROM gold_fact_sales f
    JOIN gold_dim_customer c ON c.customer_key = f.customer_key
    WHERE f.is_revenue = 1
    GROUP BY c.customer_id, c.country
),
ref AS (SELECT MAX(last_order_date) AS as_of FROM agg),
scored AS (
    SELECT a.*,
           CAST(JULIANDAY(r.as_of) - JULIANDAY(a.last_order_date) AS INTEGER) AS days_since_last_order,
           NTILE(4) OVER (ORDER BY a.revenue DESC) AS revenue_quartile
    FROM agg a, ref r
)
SELECT *,
       CASE revenue_quartile WHEN 1 THEN 'VIP' WHEN 2 THEN 'Loyal' WHEN 3 THEN 'Regular' ELSE 'Low value' END AS segment
FROM scored;

-- 4) Monthly revenue by country with share of month
DROP TABLE IF EXISTS gold_mart_revenue_by_country_month;
CREATE TABLE gold_mart_revenue_by_country_month AS
WITH m AS (
    SELECT d.year_month, c.country, ROUND(SUM(f.line_amount), 2) AS revenue
    FROM gold_fact_sales f
    JOIN gold_dim_date d     ON d.date_key = f.date_key
    JOIN gold_dim_customer c ON c.customer_key = f.customer_key
    WHERE f.is_revenue = 1
    GROUP BY d.year_month, c.country
)
SELECT year_month, country, revenue,
       ROUND(100.0 * revenue / SUM(revenue) OVER (PARTITION BY year_month), 1) AS pct_of_month
FROM m;
