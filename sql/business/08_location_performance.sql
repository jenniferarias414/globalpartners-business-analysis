-- Rank restaurant locations by total order revenue.

WITH current_orders AS (
    SELECT *
    FROM globalpartners_gold.fact_order
    WHERE load_date = (
        SELECT MAX(load_date)
        FROM globalpartners_gold.fact_order
    )
),
location_summary AS (
    SELECT
        restaurant_id,
        COUNT(*) AS order_count,
        COUNT(DISTINCT order_date) AS active_sales_days,
        ROUND(SUM(order_revenue), 2) AS total_revenue,
        ROUND(AVG(CAST(order_revenue AS DOUBLE)), 2) AS average_order_value,
        COUNT(DISTINCT user_id) AS identified_customer_count,
        COUNT_IF(is_loyalty) AS loyalty_order_count
    FROM current_orders
    GROUP BY restaurant_id
)
SELECT
    DENSE_RANK() OVER (ORDER BY total_revenue DESC) AS revenue_rank,
    restaurant_id,
    order_count,
    active_sales_days,
    total_revenue,
    average_order_value,
    identified_customer_count,
    loyalty_order_count,
    ROUND(100.0 * loyalty_order_count / NULLIF(order_count, 0), 2) AS loyalty_order_percent
FROM location_summary
ORDER BY revenue_rank, restaurant_id;
