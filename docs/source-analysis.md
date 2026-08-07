# Source Analysis

## Scope

The source assessment covers three CSV extracts representing order items, order item options, and a date dimension. The analysis validates file structure, row counts, missing values, duplicate records, candidate keys, date coverage, and relationships between the files.

The source files were not modified during analysis.

## Source Inventory

| Source | Rows | Columns | Exact Repeated Rows |
|---|---:|---:|---:|
| `order_items.csv` | 203,519 | 13 | 0 |
| `order_item_options.csv` | 193,017 | 6 | 2,299 |
| `date_dim.csv` | 365 | 8 | 0 |

The documented and actual row counts match for both order extracts. All three files contain the expected columns.

## Key Assessment

| Source | Candidate Key | Result |
|---|---|---|
| `order_items.csv` | `lineitem_id` | Unique when populated, but one row is missing the value |
| `order_items.csv` | `order_id`, `lineitem_id` | Unique when populated, but the same row remains incomplete |
| `order_item_options.csv` | `order_id`, `lineitem_id` | Not unique because an order item can have multiple options |
| `order_item_options.csv` | All supplied columns | Not unique because 2,299 rows repeat exactly |
| `date_dim.csv` | `date_key` | Complete and unique |

`date_key` is a strong key candidate. `lineitem_id` is a candidate for order items but requires an exception rule for the single missing value. The options extract does not contain a complete natural key that uniquely identifies every row.

## Relationship Assessment

Of the 193,017 option rows, 28 do not match an order in `order_items`. These rows represent 14 missing order IDs and 15 order-line-item combinations.

The same 28 rows fail both the order-level and order-line-item relationship checks. They are not part of the exact repeated-row set.

## Date Coverage

Order activity spans April 21, 2020 through February 21, 2024. The supplied date dimension covers January 1 through December 31, 2023.

| Order Year | Order Item Rows | Rows Matched to Date Dimension |
|---:|---:|---:|
| 2020 | 10,226 | 0 |
| 2021 | 43,478 | 0 |
| 2022 | 60,066 | 0 |
| 2023 | 80,664 | 80,664 |
| 2024 | 9,085 | 0 |

Every 2023 order row matches the date dimension. The 122,855 unmatched rows fall outside the supplied dimension's date range.

## Missing Values Requiring Review

- One order-item row is missing `lineitem_id`, `item_category`, and `item_name`.
- `user_id` is missing from 17,808 rows.
- `printed_card_number` is missing from 157,435 rows.
- `holiday_name` is populated for 12 date records and empty for the remaining dates.

Missing customer identifiers may affect customer-level metrics. The relationship between loyalty status, user IDs, and printed card numbers requires additional validation.

## Decisions Required

Before transformation rules are finalized, the following items require confirmation:

1. Whether the curated date dimension should be extended to cover the full order history.
2. Whether exact repeated option rows should be retained, removed, or quarantined.
3. How orphan option records should be handled.
4. How the order-item row with a missing `lineitem_id` should be handled.
5. How missing customer identifiers should affect customer-level analysis.