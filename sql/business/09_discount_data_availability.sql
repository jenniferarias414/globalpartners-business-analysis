-- Document the evidence available for discount and profitability analysis.
-- The supplied source has item and option prices, but no explicit discount,
-- standard-price, promotion, or product-cost fields.

WITH current_orders AS (
    SELECT *
    FROM globalpartners_gold.fact_order
    WHERE load_date = (
        SELECT MAX(load_date)
        FROM globalpartners_gold.fact_order
    )
)
SELECT
    COUNT(*) AS order_count,
    COUNT_IF(item_revenue < 0) AS orders_with_negative_item_revenue,
    COUNT_IF(option_revenue < 0) AS orders_with_negative_option_revenue,
    COUNT_IF(order_revenue < 0) AS orders_with_negative_total_revenue,
    'NO' AS explicit_discount_field_available,
    'NO' AS standard_price_field_available,
    'NO' AS product_cost_field_available,
    'Discount and profitability metrics are not supported by the supplied fields.' AS supported_conclusion
FROM current_orders;
