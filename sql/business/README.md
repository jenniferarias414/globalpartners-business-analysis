# Business SQL Queries

These Amazon Athena queries analyze the latest complete Gold snapshot in the
`globalpartners_gold` Glue database.

| File | Purpose |
|---|---|
| `02_clv_tier_summary.sql` | Summarize customers and lifetime revenue by CLV tier. |
| `03_top_customers_by_clv.sql` | List the 20 highest-value identified customers. |
| `04_customer_clv_evolution.sql` | Show daily cumulative value for the highest-value customer. |
| `05_rfm_segments_and_churn.sql` | Summarize RFM segments and churn indicators. |
| `06_monthly_sales_trends.sql` | Show monthly order and revenue trends. |
| `07_loyalty_performance.sql` | Compare loyalty and non-loyalty order performance. |
| `08_location_performance.sql` | Rank restaurant locations by revenue. |
| `09_discount_data_availability.sql` | Document whether discount and profitability analysis are supported. |

Each query filters to the maximum `load_date` so future full-snapshot pipeline
runs do not double count historical records.
