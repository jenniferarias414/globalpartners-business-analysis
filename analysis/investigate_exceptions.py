"""Investigate exceptions found during key and relationship validation."""

from __future__ import annotations

import pandas as pd

from profile_sources import (
    REPORT_DIRECTORY,
    SOURCE_DIRECTORY,
    load_source_file,
)
from validate_keys_and_relationships import normalize_dataframe


def format_date(value: pd.Timestamp) -> str:
    """Format a parsed date for a report."""
    if pd.isna(value):
        return ""
    return value.strftime("%Y-%m-%d")


def main() -> None:
    """Analyze date coverage, missing keys, and orphan option records."""
    print("Reading and normalizing source files...")

    order_items = normalize_dataframe(
        load_source_file(SOURCE_DIRECTORY / "order_items.csv")
    )
    order_item_options = normalize_dataframe(
        load_source_file(SOURCE_DIRECTORY / "order_item_options.csv")
    )
    date_dim = normalize_dataframe(
        load_source_file(SOURCE_DIRECTORY / "date_dim.csv")
    )

    # Parse each source using its documented date format.
    parsed_order_dates = pd.to_datetime(
        order_items["creation_time_utc"],
        format="ISO8601",
        errors="coerce",
        utc=True,
    )
    parsed_dimension_dates = pd.to_datetime(
        date_dim["date_key"],
        format="%d-%m-%Y",
        errors="coerce",
    )

    order_date_values = parsed_order_dates.dt.strftime("%Y-%m-%d")
    dimension_date_values = parsed_dimension_dates.dt.strftime("%Y-%m-%d")
    dimension_date_set = set(dimension_date_values.dropna())

    # Summarize the date boundaries of each source.
    date_range_summary = pd.DataFrame(
        [
            {
                "source": "order_items.csv",
                "minimum_date": format_date(parsed_order_dates.min()),
                "maximum_date": format_date(parsed_order_dates.max()),
                "distinct_dates": int(order_date_values.nunique()),
                "invalid_or_missing_dates": int(parsed_order_dates.isna().sum()),
            },
            {
                "source": "date_dim.csv",
                "minimum_date": format_date(parsed_dimension_dates.min()),
                "maximum_date": format_date(parsed_dimension_dates.max()),
                "distinct_dates": int(dimension_date_values.nunique()),
                "invalid_or_missing_dates": int(
                    parsed_dimension_dates.isna().sum()
                ),
            },
        ]
    )

    # Show which order years are and are not represented in date_dim.
    date_details = pd.DataFrame(
        {
            "order_year": parsed_order_dates.dt.year.astype("Int64"),
            "date_in_dimension": order_date_values.isin(dimension_date_set),
        }
    )

    date_coverage = (
        date_details.groupby("order_year", dropna=False)
        .agg(
            order_item_rows=("date_in_dimension", "size"),
            matched_date_rows=("date_in_dimension", "sum"),
        )
        .reset_index()
    )

    date_coverage["matched_date_rows"] = (
        date_coverage["matched_date_rows"].astype(int)
    )
    date_coverage["unmatched_date_rows"] = (
        date_coverage["order_item_rows"]
        - date_coverage["matched_date_rows"]
    )
    date_coverage["match_rate_percent"] = (
        date_coverage["matched_date_rows"]
        / date_coverage["order_item_rows"]
        * 100
    ).round(4)

    # Identify options whose order_id is absent from order_items.
    parent_order_ids = set(order_items["order_id"].dropna())
    orphan_order_mask = ~order_item_options["order_id"].isin(
        parent_order_ids
    )

    # Identify options whose order_id and lineitem_id pair is absent.
    parent_pairs = (
        order_items[["order_id", "lineitem_id"]]
        .dropna()
        .drop_duplicates()
        .assign(_parent_match=True)
    )

    pair_check = order_item_options[
        ["order_id", "lineitem_id"]
    ].merge(
        parent_pairs,
        how="left",
        on=["order_id", "lineitem_id"],
        validate="many_to_one",
    )

    orphan_pair_mask = pair_check["_parent_match"].isna()
    orphan_options = order_item_options.loc[orphan_pair_mask].copy()

    same_rows_fail_both_checks = (
        orphan_order_mask.reset_index(drop=True).equals(
            orphan_pair_mask.reset_index(drop=True)
        )
    )

    exception_summary = pd.DataFrame(
        [
            {
                "category": "order_items key",
                "metric": "rows_missing_lineitem_id",
                "value": int(order_items["lineitem_id"].isna().sum()),
            },
            {
                "category": "option relationship",
                "metric": "orphan_option_rows",
                "value": len(orphan_options),
            },
            {
                "category": "option relationship",
                "metric": "distinct_missing_order_ids",
                "value": int(
                    orphan_options["order_id"].nunique(dropna=True)
                ),
            },
            {
                "category": "option relationship",
                "metric": "distinct_orphan_order_lineitem_pairs",
                "value": len(
                    orphan_options[
                        ["order_id", "lineitem_id"]
                    ].drop_duplicates()
                ),
            },
            {
                "category": "option relationship",
                "metric": "same_rows_fail_order_and_lineitem_checks",
                "value": (
                    "yes" if same_rows_fail_both_checks else "no"
                ),
            },
            {
                "category": "option relationship",
                "metric": "exact_duplicate_orphan_rows_after_first",
                "value": int(
                    orphan_options.duplicated(keep="first").sum()
                ),
            },
        ]
    )

    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    date_range_path = REPORT_DIRECTORY / "date_range_summary.csv"
    date_coverage_path = REPORT_DIRECTORY / "date_coverage_by_year.csv"
    exception_summary_path = REPORT_DIRECTORY / "exception_summary.csv"

    date_range_summary.to_csv(date_range_path, index=False)
    date_coverage.to_csv(date_coverage_path, index=False)
    exception_summary.to_csv(exception_summary_path, index=False)

    print("\nDATE RANGES")
    print(date_range_summary.to_string(index=False))

    print("\nORDER DATE COVERAGE BY YEAR")
    print(date_coverage.to_string(index=False))

    print("\nKEY AND RELATIONSHIP EXCEPTIONS")
    print(exception_summary.to_string(index=False))

    print("\nREPORTS WRITTEN")
    print(date_range_path)
    print(date_coverage_path)
    print(exception_summary_path)


if __name__ == "__main__":
    main()