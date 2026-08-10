-- List the 20 identified customers with the highest lifetime revenue.

WITH current_customers AS (
    SELECT *
    FROM globalpartners_gold.customer_profile
    WHERE load_date = (
        SELECT MAX(load_date)
        FROM globalpartners_gold.customer_profile
    )
)
SELECT
    user_id,
    clv_tier,
    customer_segment,
    churn_status,
    lifetime_order_count,
    lifetime_revenue,
    average_order_value,
    days_since_last_order,
    first_order_timestamp,
    last_order_timestamp
FROM current_customers
ORDER BY lifetime_revenue DESC, user_id
LIMIT 20;
