# Gold Business Metrics Validation

## Objective

Build and reconcile business-ready tables for order revenue, customer value, customer behavior, and daily sales reporting.

## Outputs

| Gold table | Row count |
|---|---:|
| `fact_order_line` | 203,518 |
| `fact_order` | 131,328 |
| `customer_daily_clv` | 100,084 |
| `customer_profile` | 20,174 |
| `daily_sales` | 67,807 |

The customer tables use the 20,174 populated source `user_id` values. Sales records without an identified customer remain included in the line, order, and daily-sales tables.

## Revenue Reconciliation

| Measure | Amount |
|---|---:|
| Item revenue | $1,778,729.14 |
| Option revenue | $85,245.14 |
| Total line revenue | $1,863,974.28 |
| Total order revenue | $1,863,974.28 |
| Total daily-sales revenue | $1,863,974.28 |
| Identified-customer revenue | $1,690,600.00 |

All six count and revenue reconciliation checks passed. The job also found no conflicting order-level platform, restaurant, timestamp, customer, loyalty, or currency values.

Customer metrics use February 21, 2024, the maximum order date in the source, as the analysis date. RFM uses a 365-day lookback, spend change compares 90-day periods, and churn risk uses a configurable 45-day inactivity threshold.
