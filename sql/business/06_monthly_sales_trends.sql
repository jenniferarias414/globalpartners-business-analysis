-- Summarize monthly performance from the order-level Gold fact.
-- fact_order is used because it has one row per order and prevents order-count
-- duplication across item categories.

WITH current_orders AS (
    SELECT *
    FROM globalpartners_gold.fact_order
    WHERE load_date = (
        SELECT MAX(load_date)
        FROM globalpartners_gold.fact_order
    )
)
SELECT
    order_year,
    order_month,
    COUNT(*) AS order_count,
    ROUND(SUM(item_revenue), 2) AS item_revenue,
    ROUND(SUM(option_revenue), 2) AS option_revenue,
    ROUND(SUM(order_revenue), 2) AS total_revenue,
    ROUND(AVG(CAST(order_revenue AS DOUBLE)), 2) AS average_order_value,
    COUNT_IF(has_identified_customer) AS identified_customer_orders,
    COUNT_IF(is_loyalty) AS loyalty_orders
FROM current_orders
GROUP BY order_year, order_month
ORDER BY order_year, order_month;
