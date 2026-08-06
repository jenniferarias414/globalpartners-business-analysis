"""Validate candidate keys and relationships across the source files."""

from __future__ import annotations

import pandas as pd

from profile_sources import (
    REPORT_DIRECTORY,
    SOURCE_DIRECTORY,
    load_source_file,
    normalize_column,
)


def normalize_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize blanks and surrounding whitespace in every column."""
    return pd.DataFrame(
        {
            column_name: normalize_column(dataframe[column_name])
            for column_name in dataframe.columns
        }
    )


def check_candidate_key(
    dataframe: pd.DataFrame,
    table_name: str,
    candidate_name: str,
    key_columns: list[str],
) -> dict[str, object]:
    """Check whether a candidate key is complete and unique."""
    missing_key_mask = dataframe[key_columns].isna().any(axis=1)
    complete_keys = dataframe.loc[~missing_key_mask, key_columns]

    duplicate_rows_after_first = int(
        complete_keys.duplicated(keep="first").sum()
    )
    rows_in_duplicate_groups = int(
        complete_keys.duplicated(keep=False).sum()
    )

    complete_and_unique = (
        len(dataframe) > 0
        and int(missing_key_mask.sum()) == 0
        and duplicate_rows_after_first == 0
    )

    return {
        "table_name": table_name,
        "candidate_name": candidate_name,
        "key_columns": "; ".join(key_columns),
        "row_count": len(dataframe),
        "rows_with_missing_key": int(missing_key_mask.sum()),
        "complete_key_rows": len(complete_keys),
        "distinct_key_combinations": len(complete_keys.drop_duplicates()),
        "duplicate_rows_after_first": duplicate_rows_after_first,
        "rows_in_duplicate_groups": rows_in_duplicate_groups,
        "complete_and_unique": "yes" if complete_and_unique else "no",
    }


def check_relationship(
    child_dataframe: pd.DataFrame,
    parent_dataframe: pd.DataFrame,
    relationship_name: str,
    child_table: str,
    parent_table: str,
    child_columns: list[str],
    parent_columns: list[str],
) -> dict[str, object]:
    """Count child rows that do not match a parent key."""
    child_missing_mask = child_dataframe[child_columns].isna().any(axis=1)
    complete_child_keys = child_dataframe.loc[
        ~child_missing_mask, child_columns
    ].copy()

    parent_keys = (
        parent_dataframe[parent_columns]
        .dropna()
        .drop_duplicates()
        .copy()
    )

    # Rename the parent columns so the merge can use one common key list.
    parent_keys.columns = child_columns
    parent_keys["_parent_match"] = True

    relationship_result = complete_child_keys.merge(
        parent_keys,
        how="left",
        on=child_columns,
        validate="many_to_one",
    )

    unmatched_child_rows = int(
        relationship_result["_parent_match"].isna().sum()
    )
    complete_child_rows = len(complete_child_keys)
    matched_child_rows = complete_child_rows - unmatched_child_rows

    match_rate = (
        matched_child_rows / complete_child_rows * 100
        if complete_child_rows
        else 0.0
    )

    return {
        "relationship_name": relationship_name,
        "child_table": child_table,
        "parent_table": parent_table,
        "child_columns": "; ".join(child_columns),
        "parent_columns": "; ".join(parent_columns),
        "child_row_count": len(child_dataframe),
        "child_rows_with_missing_key": int(child_missing_mask.sum()),
        "complete_child_rows": complete_child_rows,
        "parent_distinct_keys": len(parent_keys),
        "matched_child_rows": matched_child_rows,
        "unmatched_child_rows": unmatched_child_rows,
        "match_rate_percent": round(match_rate, 4),
    }


def main() -> None:
    """Run key and relationship validation."""
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

    key_checks = [
        check_candidate_key(
            order_items,
            "order_items.csv",
            "lineitem_id",
            ["lineitem_id"],
        ),
        check_candidate_key(
            order_items,
            "order_items.csv",
            "order_id_and_lineitem_id",
            ["order_id", "lineitem_id"],
        ),
        check_candidate_key(
            order_item_options,
            "order_item_options.csv",
            "order_id_and_lineitem_id",
            ["order_id", "lineitem_id"],
        ),
        check_candidate_key(
            order_item_options,
            "order_item_options.csv",
            "order_lineitem_group_and_option",
            [
                "order_id",
                "lineitem_id",
                "option_group_name",
                "option_name",
            ],
        ),
        check_candidate_key(
            order_item_options,
            "order_item_options.csv",
            "all_source_columns",
            list(order_item_options.columns),
        ),
        check_candidate_key(
            date_dim,
            "date_dim.csv",
            "date_key",
            ["date_key"],
        ),
    ]

    parsed_order_dates = pd.to_datetime(
        order_items["creation_time_utc"],
        errors="coerce",
        utc=True,
    )
    parsed_dimension_dates = pd.to_datetime(
        date_dim["date_key"],
        errors="coerce",
    )

    order_dates = pd.DataFrame(
        {
            "order_date": parsed_order_dates.dt.strftime("%Y-%m-%d"),
        }
    )
    dimension_dates = pd.DataFrame(
        {
            "date_key": parsed_dimension_dates.dt.strftime("%Y-%m-%d"),
        }
    )

    relationship_checks = [
        check_relationship(
            order_item_options,
            order_items,
            "option_order_to_order",
            "order_item_options.csv",
            "order_items.csv",
            ["order_id"],
            ["order_id"],
        ),
        check_relationship(
            order_item_options,
            order_items,
            "option_lineitem_to_order_lineitem",
            "order_item_options.csv",
            "order_items.csv",
            ["order_id", "lineitem_id"],
            ["order_id", "lineitem_id"],
        ),
        check_relationship(
            order_dates,
            dimension_dates,
            "order_date_to_date_dimension",
            "order_items.csv",
            "date_dim.csv",
            ["order_date"],
            ["date_key"],
        ),
    ]

    key_report = pd.DataFrame(key_checks)
    relationship_report = pd.DataFrame(relationship_checks)

    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    key_report_path = REPORT_DIRECTORY / "key_checks.csv"
    relationship_report_path = REPORT_DIRECTORY / "relationship_checks.csv"

    key_report.to_csv(key_report_path, index=False)
    relationship_report.to_csv(relationship_report_path, index=False)

    print("\nKEY CHECKS")
    print(
        key_report[
            [
                "table_name",
                "candidate_name",
                "rows_with_missing_key",
                "distinct_key_combinations",
                "duplicate_rows_after_first",
                "complete_and_unique",
            ]
        ].to_string(index=False)
    )

    print("\nRELATIONSHIP CHECKS")
    print(
        relationship_report[
            [
                "relationship_name",
                "child_rows_with_missing_key",
                "unmatched_child_rows",
                "match_rate_percent",
            ]
        ].to_string(index=False)
    )

    print("\nREPORTS WRITTEN")
    print(key_report_path)
    print(relationship_report_path)


if __name__ == "__main__":
    main()