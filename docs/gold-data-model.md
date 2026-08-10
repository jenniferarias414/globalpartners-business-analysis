# Gold Data Model

## Purpose

The Gold layer provides business-ready datasets for customer value, customer behavior, sales trends, loyalty comparisons, and location performance. It uses accepted Silver records only.

## Confirmed Source Mappings

| Business term | Source field | Gold use |
|---|---|---|
| Customer identifier | `user_id` | Customer-level metrics when populated |
| Location identifier | `restaurant_id` | Restaurant and location analysis |
| Item revenue | `item_price` | Used directly as the extended line amount |
| Item units | `item_quantity` | Units-sold metrics |
| Option revenue | `option_price` | Added from accepted option records |
| Loyalty status | `is_loyalty` | Order and transaction comparisons |

Rows with missing `user_id` remain available for sales reporting but are excluded from customer-level tables.

## Grain

Grain defines what one row represents in a table.

For example, if one order contains a cheeseburger with extra cheese and a separate fries line:

- `fact_order_line` contains two rows: one for the cheeseburger line and one for the fries line.
- `fact_order` contains one row for the complete order.
- `customer_daily_clv` contains one row for that customer and purchase date.

Defining the grain prevents revenue from being counted more than once when tables are joined or aggregated.

## Gold Tables

| Table | Grain | Primary purpose |
|---|---|---|
| `fact_order_line` | One accepted order-item line | Combine item and accepted option revenue |
| `fact_order` | One accepted order | Provide order revenue and order-level measures |
| `customer_daily_clv` | One identified customer per purchase date | Show daily revenue and cumulative historical CLV |
| `customer_profile` | One identified customer as of the source maximum date | Provide CLV tier, RFM, churn, and spend-trend measures |
| `daily_sales` | One date, location, platform, category, loyalty status, and currency | Support time, category, loyalty, and location analysis |

### `fact_order_line`

Inputs:

- accepted Silver `order_items`;
- accepted Silver `order_item_options`, aggregated by `order_id + lineitem_id`.

Key measures and indicators:

- item amount;
- option amount;
- total line revenue;
- item quantity;
- accepted option count;
- repeated option occurrence count;
- repeated-option indicator; and
- date-dimension match indicator.

Revenue rule:

`line_revenue = item_price + sum(accepted option_price)`

`item_price` is not multiplied by `item_quantity` because the source pattern shows that price generally already includes quantity.

### `fact_order`

Input:

- Gold `fact_order_line`.

Key measures and attributes:

- order timestamp and date;
- restaurant;
- ordering platform;
- user ID when available;
- loyalty status;
- currency;
- item amount;
- option amount;
- total order revenue;
- line count;
- item quantity;
- option count; and
- repeated-option indicator.

Before aggregation, the Gold job validates that each `order_id` has one consistent restaurant, platform, timestamp, loyalty value, currency, and populated user ID.

### `customer_daily_clv`

Input:

- Gold `fact_order` records with a populated `user_id`.

Key measures:

- daily order count;
- daily revenue;
- cumulative order count; and
- cumulative historical revenue, labeled `customer_lifetime_value`.

The table records purchase dates, when customer value changes. A customer without an order on a date has no new revenue, so the cumulative value remains unchanged until the next purchase.

### `customer_profile`

Input:

- identified customers from Gold `fact_order`.

Key measures and classifications:

- first and last order timestamps;
- lifetime order count;
- lifetime revenue;
- average order value;
- days since last order;
- average gap between orders;
- recent-period revenue;
- prior-period revenue;
- spend-change percentage;
- RFM recency, frequency, and monetary measures;
- RFM scores;
- customer segment;
- CLV tier;
- churn status; and
- loyalty activity indicator.

The source maximum order date is used as the analysis date so historical data is not compared with the current calendar date.

Default configurable rules:

| Rule | Initial value |
|---|---:|
| RFM lookback | 365 days |
| Recent spend period | 90 days |
| Prior comparison period | Previous 90 days |
| At-risk inactivity threshold | More than 45 days |

These values will be job parameters so they can be changed without rewriting the transformation logic.

CLV tiers follow the project requirements:

- High: top 20% of identified customers by lifetime revenue;
- Medium: middle 60%; and
- Low: bottom 20%.

RFM values use five-point relative scores. Higher scores represent more recent activity, more orders, or more revenue.

Initial segment rules:

- VIP: recency, frequency, and monetary scores are all at least four;
- New Customer: one lifetime order and activity within the churn threshold;
- Churn Risk: last activity exceeds the configured inactivity threshold; and
- Other Active: remaining identified customers.

### `daily_sales`

Input:

- Gold `fact_order_line`.

Grouping fields:

- order date;
- restaurant ID;
- application name;
- item category;
- loyalty status; and
- currency.

Measures:

- item revenue;
- option revenue;
- total revenue;
- distinct orders;
- item lines;
- units sold; and
- identified customers.

Weekly and monthly reporting can be produced from the daily table in Athena and Streamlit without storing separate copies of the same measures.

## Dashboard Support

| Requirement | Gold source |
|---|---|
| Daily CLV evolution | `customer_daily_clv` |
| CLV tiers, RFM, and churn | `customer_profile` |
| Weekly and monthly sales trends | `daily_sales` |
| Category and platform trends | `daily_sales` |
| Loyalty comparison | `fact_order` and `daily_sales` |
| Location ranking and average order value | `fact_order` |
| Order and line-level detail | `fact_order` and `fact_order_line` |

## Date Handling

The supplied date dimension contains only 2023. The Gold job derives standard calendar fields from the order timestamp for the complete 2020–2024 order history.

Holiday fields are joined from the accepted Silver date dimension when available. Orders outside 2023 retain null holiday attributes and a false date-dimension match indicator.

## Unsupported Metrics

The source contains no negative option prices, so discounted-versus-full-price analysis cannot be calculated from the supplied records.

The source also contains no product-cost field, so profit and profitability cannot be calculated accurately.

The dashboard and documentation will state these limitations rather than populate unsupported values.

## Processing Order

1. Build `fact_order_line` from accepted Silver items and options.
2. Build `fact_order` from the line-level fact.
3. Build `customer_daily_clv` from identified orders.
4. Build `customer_profile` from identified customer history.
5. Build `daily_sales` from line-level sales activity.
6. Reconcile Gold revenue and record counts before publishing the outputs.

## Reload Handling

All Gold outputs use the same processing-date partition pattern as Bronze and Silver. A same-date rerun replaces the current Gold partitions before writing new files.

The job writes a JSON control report containing source counts, output counts, revenue reconciliation results, parameters, and output paths.
