-- Summarize Recency, Frequency, Monetary (RFM) customer segments.
-- AT_RISK means the last order was more than the configured 45-day threshold
-- before the analysis date of 2024-02-21.

WITH current_customers AS (
    SELECT *
    FROM globalpartners_gold.customer_profile
    WHERE load_date = (
        SELECT MAX(load_date)
        FROM globalpartners_gold.customer_profile
    )
)
SELECT
    customer_segment,
    COUNT(*) AS customer_count,
    COUNT_IF(churn_status = 'AT_RISK') AS at_risk_customer_count,
    ROUND(AVG(CAST(days_since_last_order AS DOUBLE)), 2) AS average_days_since_last_order,
    ROUND(AVG(CAST(lifetime_order_count AS DOUBLE)), 2) AS average_lifetime_orders,
    ROUND(SUM(lifetime_revenue), 2) AS total_lifetime_revenue,
    ROUND(AVG(CAST(lifetime_revenue AS DOUBLE)), 2) AS average_lifetime_revenue,
    ROUND(AVG(CAST(rfm_recency_score AS DOUBLE)), 2) AS average_recency_score,
    ROUND(AVG(CAST(rfm_frequency_score AS DOUBLE)), 2) AS average_frequency_score,
    ROUND(AVG(CAST(rfm_monetary_score AS DOUBLE)), 2) AS average_monetary_score
FROM current_customers
GROUP BY customer_segment
ORDER BY total_lifetime_revenue DESC;
