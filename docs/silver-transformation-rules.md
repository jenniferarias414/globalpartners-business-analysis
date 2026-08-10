# Silver Transformation Rules

## Purpose

The Silver layer converts the source-aligned Bronze snapshots into typed, validated datasets for downstream analysis. Each source table is processed by a separate AWS Glue PySpark job so failures and reloads can be controlled independently.

The Silver layer will not silently remove records based on unresolved business assumptions. Records that cannot support a valid relationship or key will be quarantined. Records with known but usable limitations will be retained with quality flags.

## Job Structure

| Job | Input | Accepted Output | Quarantine Output |
|---|---|---|---|
| `globalpartners-silver-date-dim` | Bronze `date_dim` | `silver/date_dim/load_date=YYYY-MM-DD/` | No records expected |
| `globalpartners-silver-order-items` | Bronze `order_items` | `silver/order_items/load_date=YYYY-MM-DD/` | `quarantine/silver/order_items/load_date=YYYY-MM-DD/` |
| `globalpartners-silver-order-item-options` | Bronze `order_item_options` and accepted Silver `order_items` keys | `silver/order_item_options/load_date=YYYY-MM-DD/` | `quarantine/silver/order_item_options/load_date=YYYY-MM-DD/` |

The date and order-item jobs can run after Bronze succeeds. The option job runs after the order-item job because it uses accepted `(order_id, lineitem_id)` pairs to validate parent relationships.

The Gold job will start only after all three Silver jobs succeed.

## Shared Processing Rules

All Silver jobs will:

1. Read the Bronze partition supplied through `--load_date`.
2. Preserve the Bronze lineage fields.
3. Trim surrounding whitespace from string fields.
4. Convert empty strings to null values.
5. Apply explicit data types.
6. Add `_silver_processed_at_utc` and `_quality_status` fields.
7. Write accepted and quarantined records to separate S3 prefixes.
8. Replace current output for the same processing date during a reload.
9. Write a JSON control document containing input, accepted, quarantined, and output counts.
10. Fail the job if the reconciliation rule does not pass.

For every table:

`input rows = accepted rows + quarantined rows`

## Date Dimension Rules

### Data Types

| Column | Silver Type |
|---|---|
| `date_key` | Date |
| `year` | Integer |
| `month` | Integer |
| `week` | Integer |
| `day_of_week` | String |
| `is_weekend` | Boolean |
| `is_holiday` | Boolean |
| `holiday_name` | String, nullable |

### Validation

A date record is accepted when:

- `date_key` is present and valid.
- `date_key` is unique within the snapshot.
- `year`, `month`, `week`, and `day_of_week` agree with `date_key`.
- `is_weekend` agrees with the day represented by `date_key`.
- Holiday records have a holiday name.
- Non-holiday records do not contain a holiday name.

The supplied file passes these checks for all 365 rows.

### Coverage Rule

The supplied dimension covers January 1 through December 31, 2023, while orders cover April 21, 2020 through February 21, 2024.

The Silver job will preserve the supplied 2023 date dimension rather than invent holiday information for missing years. Orders outside 2023 will not be quarantined. Gold time summaries can derive standard calendar fields from `creation_time_utc`, while holiday analysis will be limited to dates supplied in the dimension.

### Expected Initial Result

| Input | Accepted | Quarantined |
|---:|---:|---:|
| 365 | 365 | 0 |

## Order Item Rules

### Data Types

| Column | Silver Type |
|---|---|
| `app_name` | String |
| `restaurant_id` | String |
| `creation_time_utc` | Timestamp |
| `order_id` | String |
| `user_id` | String, nullable |
| `printed_card_number` | String, nullable |
| `is_loyalty` | Boolean |
| `currency` | String |
| `lineitem_id` | String |
| `item_category` | String |
| `item_name` | String |
| `item_price` | Decimal |
| `item_quantity` | Integer |

### Standardized Business Aliases

The Silver table will retain the source columns and add:

- `customer_id` as an alias of `user_id`.
- `location_id` as an alias of `restaurant_id`.

No loyalty-card fallback will be used when `user_id` is missing. Treating two identifiers as the same customer without a documented crosswalk could merge or split customers incorrectly.

### Quarantine Rules

An order-item row is quarantined if any of these conditions apply:

- `order_id` is missing.
- `lineitem_id` is missing.
- `restaurant_id` is missing.
- `creation_time_utc` is invalid.
- `item_category` is missing.
- `item_name` is missing.
- `item_price` cannot be converted to a decimal or is negative.
- `item_quantity` cannot be converted to an integer or is less than or equal to zero.

Each quarantined row will include `_quarantine_reason_codes` containing every rule it failed.

One supplied row fails because it has a missing `lineitem_id`, missing item category, missing item name, and zero item quantity.

### Retained Quality Flags

The following conditions do not invalidate the transaction and will not cause quarantine:

- Missing `user_id`: retain the row and set `is_customer_identified` to false.
- Missing `printed_card_number` for a non-loyalty row: treat as expected.
- Zero `item_price`: retain because the source does not state that complimentary items are invalid.
- High item quantities or prices: retain because the data includes bulk and catering activity and no approved upper limit is supplied.
- Development platform name: retain and set `is_development_channel` when `app_name` contains `DEVELOPMENT`.
- Order date outside the supplied 2023 date dimension: retain and set `has_date_dimension_match` to false.

Customer-level metrics will use records with a populated `customer_id`. Rows without a customer identifier remain available for overall sales and operational totals.

### Price Interpretation

The requirements describe `item_price` as a unit price. The actual multi-quantity records strongly indicate that it frequently represents the extended line amount. For example, a quantity of 500 with an `item_price` of 5,000 implies a $10 unit amount.

The Silver job will preserve `item_price` and `item_quantity` without calculating revenue. The Gold metric logic must document the selected interpretation before calculating CLV or sales totals. Multiplying the two fields without resolving this contradiction could substantially overstate revenue.

### Expected Initial Result

| Input | Accepted | Quarantined |
|---:|---:|---:|
| 203,519 | 203,518 | 1 |

Additional retained conditions:

- 17,808 rows have no `user_id` and will receive `is_customer_identified = false`.
- 826 rows use the development platform name and will receive `is_development_channel = true`.
- 122,854 accepted rows fall outside the supplied date-dimension range and will receive `has_date_dimension_match = false`. The Bronze total is 122,855, but one of those rows is the separately quarantined invalid order item.

## Order Item Option Rules

### Data Types

| Column | Silver Type |
|---|---|
| `order_id` | String |
| `lineitem_id` | String |
| `option_group_name` | String |
| `option_name` | String |
| `option_price` | Decimal |
| `option_quantity` | Integer |

### Parent Relationship

An option is valid only when its `(order_id, lineitem_id)` pair exists in the accepted Silver order-item data for the same processing date.

The two-column pair is required because an order can contain multiple line items. Matching only `order_id` would show that the order exists but would not prove that the option belongs to a valid item within that order.

### Quarantine Rules

An option row is quarantined if any of these conditions apply:

- `order_id` is missing.
- `lineitem_id` is missing.
- `option_group_name` is missing.
- `option_name` is missing.
- `option_price` cannot be converted to a decimal.
- `option_quantity` cannot be converted to an integer or is less than or equal to zero.
- The `(order_id, lineitem_id)` parent pair is not present in accepted Silver order items.

The 28 supplied orphan option rows will be quarantined with `MISSING_PARENT_ORDER_ITEM`. They reference 14 missing orders and 15 missing order-line pairs.

### Exact Repeated Rows

The source contains:

- 616 repeated-value groups.
- 2,915 total rows within those groups.
- 2,299 occurrences beyond the first row in each group.
- Up to 10 identical rows in one group.

The source does not provide an option-level key or rule proving these are accidental duplicates. They may represent repeated selections of the same modifier.

The Silver job will retain these rows and add:

- `exact_repeat_count`: number of identical source rows in the processing-date snapshot.
- `has_exact_repeats`: true when `exact_repeat_count` is greater than one.

The pipeline will not silently deduplicate them. Gold calculations that use option revenue must state whether repeated rows are counted or excluded.

### Discount Flag

The Silver table will add `is_discount` when `option_price` is less than zero.

The supplied data contains no negative option prices. Therefore, the documented discount comparison cannot produce a discounted group from the current snapshot. Zero-priced options are not automatically classified as discounts.

### Expected Initial Result

| Input | Accepted | Quarantined |
|---:|---:|---:|
| 193,017 | 192,989 | 28 |

The 2,299 repeated occurrences remain in the accepted output with repeat flags because the source does not prove they are invalid.

## Reload and Reconciliation

Each Silver job will receive the same `--load_date` as the Bronze job.

For a same-date reload, the job will replace the current accepted, quarantine, and control outputs for that table and date. S3 versioning will retain earlier object versions for recovery.

The control document will record:

- Input row count
- Accepted row count
- Quarantined row count
- Quality-flag counts
- Output paths
- Run ID
- Processing date
- Completion status

A job succeeds only when its expected reconciliation checks pass.

## Rules Deferred to the Gold Layer

The following decisions are not Silver cleansing rules:

- Final revenue interpretation for `item_price`
- Treatment of exact repeated options in revenue
- Customer-value percentile assignment
- RFM lookback period and scoring thresholds
- Churn inactivity thresholds
- Profitability calculations without product-cost data
- Discount comparison when no negative option prices are present

These items affect business metrics and must be documented when the Gold model is defined.
