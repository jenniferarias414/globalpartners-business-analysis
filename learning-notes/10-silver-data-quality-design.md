# Silver Data Quality Design

## Objective

Define consistent acceptance, quality-flag, quarantine, reconciliation, and reload rules before implementing the Silver PySpark jobs.

## Design Approach

Each source table will have a separate Silver job so it can be validated, rerun, and monitored independently. The jobs will apply explicit data types, normalize null values, preserve lineage, and separate accepted records from records that cannot support reliable analysis.

Usable records with known limitations will be retained with quality flags. Records will not be removed solely because a business rule has not been confirmed.

## Expected Results

| Table | Input Rows | Accepted Rows | Quarantined Rows |
|---|---:|---:|---:|
| `date_dim` | 365 | 365 | 0 |
| `order_items` | 203,519 | 203,518 | 1 |
| `order_item_options` | 193,017 | 192,989 | 28 |

The invalid order-item row is missing its line-item identifier and item details and has a zero quantity. The 28 quarantined options do not have a valid parent `(order_id, lineitem_id)` in the accepted order-item data.

## Retained Quality Conditions

- Orders without `user_id` remain available for overall sales analysis but will not be used as identified customers.
- Development-channel records remain available and receive a flag.
- Orders outside the supplied 2023 date dimension remain available and receive a date-match flag.
- Repeated option rows remain available with repeat-count flags because the source does not prove they are accidental duplicates.
- Zero-priced items remain available because the source does not state that complimentary items are invalid.

## Business Rules Deferred to Gold

The requirements describe `item_price` as a unit price, but multi-quantity values suggest it may represent a line amount. Silver will preserve the source price and quantity without calculating revenue.

The current options data also contains no negative prices, so it cannot produce the documented discounted-order comparison.

Revenue interpretation, repeated-option treatment, customer scoring, churn thresholds, and profitability rules will be documented during Gold model development.

## Processing Order

The date and order-item jobs can run after Bronze succeeds. The option job will run after the order-item job because it needs accepted parent keys. Gold processing will begin only after all three Silver jobs succeed.

## Result

The Silver implementation now has documented, source-supported rules for accepted data, retained limitations, quarantine handling, row-count reconciliation, and same-date reloads.
