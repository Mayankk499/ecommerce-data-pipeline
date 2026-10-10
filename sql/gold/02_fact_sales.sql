-- GOLD: fact table. Grain = one row per order line.
-- `is_revenue` flags lines that count as revenue (completed / shipped);
-- cancelled and returned orders are kept for analysis but excluded from revenue.
DROP TABLE IF EXISTS gold_fact_sales;
CREATE TABLE gold_fact_sales AS
SELECT o.order_id,
       c.customer_key,
       p.product_key,
       CAST(STRFTIME('%Y%m%d', o.order_ts) AS INTEGER) AS date_key,
       o.order_ts,
       o.status,
       o.payment_method,
       i.quantity,
       i.unit_price,
       ROUND(i.quantity * i.unit_price, 2) AS line_amount,
       CASE WHEN o.status IN ('completed', 'shipped') THEN 1 ELSE 0 END AS is_revenue
FROM silver_order_items i
JOIN silver_orders     o ON o.order_id   = i.order_id
JOIN gold_dim_customer c ON c.customer_id = o.customer_id
JOIN gold_dim_product  p ON p.product_id  = i.product_id;

CREATE UNIQUE INDEX idx_fact_pk       ON gold_fact_sales(order_id, product_key);
CREATE INDEX        idx_fact_date     ON gold_fact_sales(date_key);
CREATE INDEX        idx_fact_customer ON gold_fact_sales(customer_key);
