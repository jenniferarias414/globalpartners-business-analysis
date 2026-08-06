# Initial Source Profiling

## Purpose

The initial profiling step validated the three supplied CSV files before designing the data model or AWS pipeline. The source files were analyzed locally without modifying their contents.

## Profiling Process

The `analysis/profile_sources.py` script:

* Confirms that all expected files are available.
* Compares row counts and columns with the project requirements.
* Creates a SHA-256 fingerprint for each file.
* Measures missing values, distinct values, and duplicate rows.
* Identifies columns that may qualify as single-column keys.
* Writes detailed results to local generated reports.

The files were read as strings to preserve identifiers and source formatting. Column names were standardized to lowercase inside the analysis process because the transactional files use uppercase headers.

## Running the Profile

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m py_compile analysis/profile_sources.py
python analysis/profile_sources.py
```

Generated reports:

* `reports/generated/source_inventory.csv`
* `reports/generated/column_profile.csv`

The generated reports remain local and are excluded from Git.

## Initial Results

| Source                   | Required Rows | Actual Rows | Schema Match | Repeated Rows After First |
| ------------------------ | ------------: | ----------: | ------------ | ------------------------: |
| `order_items.csv`        |       203,519 |     203,519 | Yes          |                         0 |
| `order_item_options.csv` |       193,017 |     193,017 | Yes          |                     2,299 |
| `date_dim.csv`           |    Not stated |         365 | Yes          |                         0 |

Additional observations:

* `date_key` is complete and unique across all 365 date records.
* `lineitem_id` has one missing value; all populated values are distinct.
* `user_id` is missing from 17,808 order-item rows, or 8.75%.
* `printed_card_number` is missing from 77.36% of order-item rows.
* No single column qualifies as a complete and unique key in `order_item_options`.
* `holiday_name` is populated for 12 of the 365 date records.

## Next Validation

The next profiling step will test composite keys and relationships between the three sources. It will also examine the repeated option records, incomplete customer identifiers, loyalty-card coverage, and date relationships before findings are finalized.
