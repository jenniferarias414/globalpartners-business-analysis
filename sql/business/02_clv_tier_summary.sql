-- Summarize identified customers by Customer Lifetime Value (CLV) tier.
-- CLV is the customer's cumulative order revenue in the available history.

WITH current_customers AS (
    SELECT *
    FROM globalpartners_gold.customer_profile
    WHERE load_date = (
        SELECT MAX(load_date)
        FROM globalpartners_gold.customer_profile
    )
),
totals AS (
    SELECT SUM(lifetime_revenue) AS total_identified_revenue
    FROM current_customers
    
)
SELECT
    clv_tier,
    COUNT(*) AS customer_count,
    ROUND(AVG(CAST(lifetime_order_count AS DOUBLE)), 2) AS average_orders,
    ROUND(AVG(CAST(lifetime_revenue AS DOUBLE)), 2) AS average_lifetime_revenue,
    ROUND(SUM(lifetime_revenue), 2) AS total_lifetime_revenue,
    ROUND(
        100.0 * SUM(lifetime_revenue) / NULLIF(t.total_identified_revenue, 0),
        2
    ) AS identified_revenue_percent
FROM current_customers
CROSS JOIN totals t
GROUP BY clv_tier, t.total_identified_revenue
ORDER BY
    CASE clv_tier
        WHEN 'HIGH' THEN 1
        WHEN 'MEDIUM' THEN 2
        WHEN 'LOW' THEN 3
        ELSE 4
    END;
