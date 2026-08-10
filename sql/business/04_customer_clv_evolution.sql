-- Show how cumulative order count and customer value changed over time for
-- the highest-value identified customer in the latest Gold snapshot.

WITH current_customers AS (
    SELECT *
    FROM globalpartners_gold.customer_profile
    WHERE load_date = (
        SELECT MAX(load_date)
        FROM globalpartners_gold.customer_profile
    )
),
top_customer AS (
    SELECT user_id
    FROM current_customers
    ORDER BY lifetime_revenue DESC, user_id
    LIMIT 1
),
current_daily_clv AS (
    SELECT *
    FROM globalpartners_gold.customer_daily_clv
    WHERE load_date = (
        SELECT MAX(load_date)
        FROM globalpartners_gold.customer_daily_clv
    )
)
SELECT
    d.user_id,
    d.order_date,
    d.daily_order_count,
    d.daily_revenue,
    d.cumulative_order_count,
    d.customer_lifetime_value
FROM current_daily_clv d
INNER JOIN top_customer t
    ON d.user_id = t.user_id
ORDER BY d.order_date;
