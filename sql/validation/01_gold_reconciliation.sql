-- Validate Gold row counts and revenue totals for one processing partition.

WITH line_metrics AS (
    SELECT
        COUNT(*) AS fact_order_line_rows,
        ROUND(SUM(item_revenue), 2) AS item_revenue,
        ROUND(SUM(option_revenue), 2) AS option_revenue,
        ROUND(SUM(line_revenue), 2) AS line_revenue
    FROM globalpartners_gold.fact_order_line
    WHERE load_date = '2026-08-10'
),
order_metrics AS (
    SELECT
        COUNT(*) AS fact_order_rows,
        COUNT_IF(user_id IS NOT NULL) AS identified_order_rows,
        ROUND(SUM(order_revenue), 2) AS order_revenue,
        ROUND(
            SUM(CASE WHEN user_id IS NOT NULL THEN order_revenue ELSE 0 END),
            2
        ) AS identified_order_revenue
    FROM globalpartners_gold.fact_order
    WHERE load_date = '2026-08-10'
),
customer_metrics AS (
    SELECT
        COUNT(*) AS customer_profile_rows,
        ROUND(SUM(lifetime_revenue), 2) AS customer_lifetime_revenue
    FROM globalpartners_gold.customer_profile
    WHERE load_date = '2026-08-10'
),
customer_daily_metrics AS (
    SELECT COUNT(*) AS customer_daily_clv_rows
    FROM globalpartners_gold.customer_daily_clv
    WHERE load_date = '2026-08-10'
),
daily_sales_metrics AS (
    SELECT
        COUNT(*) AS daily_sales_rows,
        ROUND(SUM(total_revenue), 2) AS daily_sales_revenue
    FROM globalpartners_gold.daily_sales
    WHERE load_date = '2026-08-10'
)
SELECT
    line_metrics.fact_order_line_rows,
    order_metrics.fact_order_rows,
    order_metrics.identified_order_rows,
    customer_daily_metrics.customer_daily_clv_rows,
    customer_metrics.customer_profile_rows,
    daily_sales_metrics.daily_sales_rows,
    line_metrics.item_revenue,
    line_metrics.option_revenue,
    line_metrics.line_revenue,
    order_metrics.order_revenue,
    order_metrics.identified_order_revenue,
    customer_metrics.customer_lifetime_revenue,
    daily_sales_metrics.daily_sales_revenue
FROM line_metrics
CROSS JOIN order_metrics
CROSS JOIN customer_metrics
CROSS JOIN customer_daily_metrics
CROSS JOIN daily_sales_metrics;
