# Silver Order Items Validation

## Objective

Validate Bronze order-item records while preserving usable sales data and separating records that cannot support reliable item-level analysis.

## Processing

The AWS Glue PySpark job:

- read the Bronze `order_items` partition and accepted Silver date dimension;
- standardized strings, timestamps, Boolean values, prices, and quantities;
- checked required item fields and line-item uniqueness;
- quarantined records with blocking data-quality failures;
- retained usable records with customer, application, and date-coverage flags;
- reconciled the input, accepted, and quarantined counts; and
- wrote a JSON control report for the run.

## Validation Results

| Measure | Result |
|---|---:|
| Bronze input rows | 203,519 |
| Silver accepted rows | 203,518 |
| Quarantined rows | 1 |
| Reconciliation passed | Yes |

The quarantined record was missing its line-item identifier, item category, and item name and had a non-positive quantity.

The job retained records with non-blocking conditions and added flags for 17,808 missing user IDs, 157,435 missing printed card numbers, 122,855 order dates outside the supplied 2023 date dimension, and 826 development-application records.

These flags preserve sales records that remain useful for product, location, and order analysis while identifying limitations for customer-level or date-dimension reporting.
