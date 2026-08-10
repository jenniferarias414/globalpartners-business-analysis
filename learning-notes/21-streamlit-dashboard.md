# Streamlit Business Dashboard

## Objective

Present the validated Gold business metrics in a browser-based dashboard that
can run locally or temporarily on Amazon EC2.

## Dashboard Design

The Streamlit application queries the latest snapshot in the Athena
`globalpartners_gold` database. It contains four business views:

1. Executive Overview
2. Customer and CLV
3. Sales and Loyalty
4. Location Performance

The Executive Overview summarizes revenue, orders, average order value,
identified customers, units, and monthly trends. The other views provide CLV
tiers, RFM segments, churn indicators, loyalty comparisons, sales channels, and
location rankings.

## Query Approach

The dashboard uses `fact_order` for order-level totals and
`customer_profile` for customer-level metrics. Every query filters to the
latest `load_date` partition so repeated snapshots are not combined.

The first dashboard version summed `order_count` from `daily_sales`. That field
is calculated within several reporting dimensions and is not additive across
all groups. The final dashboard counts rows from `fact_order`, which reconciles
to 131,328 orders and produces the validated $14.19 average order value.

## Confirmed Results

- Total revenue: $1,863,974.28
- Orders: 131,328
- Average order value: $14.19
- Identified customers: 20,174
- Units sold: 227,487
- Loyalty order share: 23.87%
- Loyalty revenue share: 22.72%
- Represented locations: 28

CLV tiers total 20,174 customers. Loyalty and non-loyalty results independently
reconcile to the complete order and revenue totals.

## Runtime and Cost Controls

Athena results are cached for 15 minutes to reduce repeated queries. The
sidebar refresh control clears the cache and reruns the queries when current
results are needed.

Local execution uses the named `retail-poc` AWS profile. EC2 execution omits a
named profile and uses the instance's attached IAM role. Athena queries stop
after three minutes if they do not complete.

## Data Limitations

- Customer metrics exclude orders without `user_id`.
- Location labels are source `restaurant_id` values because names and address
  attributes were not supplied.
- February 2024 and April 2020 are partial months.
- Discount and profitability metrics are excluded because the source does not
  provide discount, standard-price, or product-cost fields.
- The 45-day churn rule and other RFM parameters are documented project
  assumptions that require business confirmation.
