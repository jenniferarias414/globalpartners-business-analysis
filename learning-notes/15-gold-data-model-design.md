# Gold Data Model Design

## Objective

Define business-ready Gold tables with clear row-level meaning before building customer, order, and sales metrics.

## Model

The Gold layer will contain five datasets:

| Table | One row represents |
|---|---|
| `fact_order_line` | One accepted order-item line with accepted option revenue |
| `fact_order` | One complete order |
| `customer_daily_clv` | One identified customer on one purchase date |
| `customer_profile` | One identified customer as of the source maximum date |
| `daily_sales` | One daily sales grouping by location, platform, category, loyalty, and currency |

This design supports daily historical CLV, customer tiers, RFM, churn indicators, sales trends, loyalty comparisons, and location performance without creating a separate physical table for every chart.

## Key Decisions

- Source `user_id` serves as the customer identifier.
- Rows without `user_id` remain in sales tables but are excluded from customer tables.
- Source `restaurant_id` serves as the location identifier.
- `item_price` is used directly as the item line amount.
- Accepted option prices are aggregated to their parent line item.
- Repeated options remain included and flagged.
- Standard calendar fields are derived for the full order history.
- Holiday attributes are available only where the supplied 2023 date dimension matches.
- RFM, spend-period, and churn thresholds are configurable job parameters.

The design does not calculate discount effectiveness because no negative option prices were supplied. It does not calculate profitability because the source contains no product-cost field.
