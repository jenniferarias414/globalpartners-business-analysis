-- Compare order performance by the order-level loyalty flag.
-- Customer counts include only orders with a populated user_id.

WITH current_orders AS (
    SELECT *
    FROM globalpartners_gold.fact_order
    WHERE load_date = (
        SELECT MAX(load_date)
        FROM globalpartners_gold.fact_order
    )
),
order_summary AS (
    SELECT
        CASE
            WHEN is_loyalty THEN 'LOYALTY_ORDER'
            ELSE 'NON_LOYALTY_ORDER'
        END AS loyalty_group,
        COUNT(*) AS order_count,
        ROUND(SUM(order_revenue), 2) AS total_revenue,
        ROUND(AVG(CAST(order_revenue AS DOUBLE)), 2) AS average_order_value,
        COUNT_IF(user_id IS NULL) AS orders_without_user_id
    FROM current_orders
    GROUP BY 1
),
customer_activity AS (
    SELECT
        CASE
            WHEN is_loyalty THEN 'LOYALTY_ORDER'
            ELSE 'NON_LOYALTY_ORDER'
        END AS loyalty_group,
        user_id,
        COUNT(*) AS customer_order_count,
        SUM(order_revenue) AS customer_revenue
    FROM current_orders
    WHERE user_id IS NOT NULL
    GROUP BY 1, user_id
),
customer_summary AS (
    SELECT
        loyalty_group,
        COUNT(*) AS identified_customer_count,
        COUNT_IF(customer_order_count > 1) AS repeat_customer_count,
        ROUND(AVG(CAST(customer_order_count AS DOUBLE)), 2) AS average_orders_per_customer,
        ROUND(AVG(CAST(customer_revenue AS DOUBLE)), 2) AS average_revenue_per_customer
    FROM customer_activity
    GROUP BY loyalty_group
)
SELECT
    o.loyalty_group,
    o.order_count,
    o.total_revenue,
    o.average_order_value,
    o.orders_without_user_id,
    c.identified_customer_count,
    c.repeat_customer_count,
    c.average_orders_per_customer,
    c.average_revenue_per_customer
FROM order_summary o
LEFT JOIN customer_summary c
    ON o.loyalty_group = c.loyalty_group
ORDER BY o.loyalty_group;
