# Athena Business Analysis

## Objective

Use Amazon Athena to analyze the latest Gold snapshot and confirm that the
curated tables support the requested customer and business metrics.

## Query Design

Eight SQL queries were created for CLV tiers, top customers, daily CLV,
RFM and churn, monthly sales, loyalty performance, location performance, and
discount-data availability. Each query filters to the latest `load_date` so
future full-snapshot loads do not double count historical data.

## Validated Results

- The queries completed successfully in the `globalpartners-analysis` workgroup.
- The CLV and RFM results contain 20,174 identified customers and reconcile to
  $1,690,600.00 in identified-customer revenue.
- Monthly and loyalty results reconcile to 131,328 orders and $1,863,974.28 in
  total revenue.
- High-CLV customers represent 4,034 customers and 76.76% of identified-customer
  revenue.
- The supplied history covers 47 calendar months from April 2020 through
  February 2024.
- Discount and profitability metrics are not supported because the supplied
  fields do not include an explicit discount, standard price, or product cost.

## Interpretation Limits

The RFM lookback, spend-comparison periods, and churn threshold are configurable
project parameters rather than confirmed business rules. February 2024 is a
partial month through February 21. Loyalty is an order-level flag, so the same
customer may appear in both loyalty and non-loyalty activity.
