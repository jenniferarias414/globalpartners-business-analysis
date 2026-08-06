"""Profile the GlobalPartners source CSV files without modifying them."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = PROJECT_ROOT / "project-assets" / "source-downloads"
REPORT_DIRECTORY = PROJECT_ROOT / "reports" / "generated"


SOURCE_SPECS = {
    "order_items.csv": {
        "expected_rows": 203_519,
        "columns": {
            "app_name": "String",
            "restaurant_id": "String / Int",
            "creation_time_utc": "Timestamp",
            "order_id": "String / Int",
            "user_id": "String / Int",
            "printed_card_number": "String",
            "is_loyalty": "Boolean",
            "currency": "String",
            "lineitem_id": "String / Int",
            "item_category": "String",
            "item_name": "String",
            "item_price": "Decimal",
            "item_quantity": "Integer",
        },
    },
    "order_item_options.csv": {
        "expected_rows": 193_017,
        "columns": {
            "order_id": "String / Int",
            "lineitem_id": "String / Int",
            "option_group_name": "String",
            "option_name": "String",
            "option_price": "Decimal",
            "option_quantity": "Integer",
        },
    },
    "date_dim.csv": {
        "expected_rows": None,
        "columns": {
            "date_key": "Date",
            "day_of_week": "String",
            "week": "Integer",
            "month": "String",
            "year": "Integer",
            "is_weekend": "Boolean",
            "is_holiday": "Boolean",
            "holiday_name": "String",
        },
    },
}


def calculate_sha256(file_path: Path) -> str:
    """Return a SHA-256 fingerprint for a source file."""

    file_hash = hashlib.sha256()

    with file_path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            file_hash.update(chunk)

    return file_hash.hexdigest()


def normalize_column(series: pd.Series) -> pd.Series:
    """Trim surrounding whitespace and treat empty strings as missing."""

    trimmed_series = series.astype("string").str.strip()
    return trimmed_series.mask(trimmed_series.eq(""), pd.NA)


def format_sample_values(series: pd.Series, limit: int = 3) -> str:
    """Return a short, local-only sample of distinct non-null values."""

    sample_values = (
        series.dropna()
        .drop_duplicates()
        .head(limit)
        .astype(str)
        .tolist()
    )

    cleaned_values = []

    for value in sample_values:
        cleaned_value = (
            value.replace("\r", "\\r")
            .replace("\n", "\\n")
        )
        cleaned_values.append(cleaned_value[:80])

    return " | ".join(cleaned_values)


def load_source_file(file_path: Path) -> pd.DataFrame:
    """Read a CSV as strings so identifiers and source formatting are preserved."""

    dataframe = pd.read_csv(
        file_path,
        dtype="string",
        keep_default_na=True,
        skip_blank_lines=False,
        on_bad_lines="error",
        low_memory=False,
    )

    dataframe.columns = [
        str(column_name).strip().lower()
        for column_name in dataframe.columns
    ]

    if len(dataframe.columns) != len(set(dataframe.columns)):
        raise ValueError(
            f"Duplicate column names detected after trimming: {file_path.name}"
        )

    return dataframe


def build_inventory_row(
    file_path: Path,
    dataframe: pd.DataFrame,
    source_spec: dict,
    normalized_dataframe: pd.DataFrame,
) -> dict:
    """Build one file-level inventory result."""

    expected_columns = list(source_spec["columns"].keys())
    actual_columns = list(dataframe.columns)

    missing_columns = [
        column
        for column in expected_columns
        if column not in actual_columns
    ]

    unexpected_columns = [
        column
        for column in actual_columns
        if column not in expected_columns
    ]

    expected_rows = source_spec["expected_rows"]
    actual_rows = len(dataframe)

    if expected_rows is None:
        row_count_match = "not provided"
    elif actual_rows == expected_rows:
        row_count_match = "yes"
    else:
        row_count_match = "no"

    return {
        "file_name": file_path.name,
        "file_size_mb": round(
            file_path.stat().st_size / (1024 * 1024),
            3,
        ),
        "sha256": calculate_sha256(file_path),
        "requirements_row_count": (
            expected_rows if expected_rows is not None else ""
        ),
        "actual_row_count": actual_rows,
        "row_count_matches_requirement": row_count_match,
        "column_count": len(actual_columns),
        "missing_expected_columns": (
            "; ".join(missing_columns) if missing_columns else "None"
        ),
        "unexpected_columns": (
            "; ".join(unexpected_columns) if unexpected_columns else "None"
        ),
        "duplicate_rows_after_first": int(
            dataframe.duplicated(keep="first").sum()
        ),
        "rows_in_duplicate_groups": int(
            dataframe.duplicated(keep=False).sum()
        ),
        "normalized_duplicate_rows_after_first": int(
            normalized_dataframe.duplicated(keep="first").sum()
        ),
    }


def build_column_profile_rows(
    file_name: str,
    dataframe: pd.DataFrame,
    normalized_dataframe: pd.DataFrame,
    source_spec: dict,
) -> list[dict]:
    """Build column-level completeness and uniqueness results."""

    profile_rows = []
    row_count = len(dataframe)

    for column_name in dataframe.columns:
        raw_series = dataframe[column_name]
        normalized_series = normalized_dataframe[column_name]

        raw_null_count = int(raw_series.isna().sum())

        whitespace_mask = (
            raw_series.notna()
            & raw_series.str.strip().eq("")
        )

        whitespace_only_count = int(
            whitespace_mask.fillna(False).sum()
        )

        normalized_null_count = int(
            normalized_series.isna().sum()
        )

        non_null_series = normalized_series.dropna()
        non_null_count = len(non_null_series)

        distinct_non_null = int(
            non_null_series.nunique(dropna=True)
        )

        if row_count == 0:
            null_percent = 0.0
        else:
            null_percent = round(
                normalized_null_count / row_count * 100,
                4,
            )

        if non_null_count == 0:
            uniqueness_percent = 0.0
        else:
            uniqueness_percent = round(
                distinct_non_null / non_null_count * 100,
                4,
            )

        complete_and_unique = (
            row_count > 0
            and normalized_null_count == 0
            and distinct_non_null == row_count
        )

        documented_type = source_spec["columns"].get(
            column_name,
            "Not documented",
        )

        profile_rows.append(
            {
                "file_name": file_name,
                "column_name": column_name,
                "documented_data_type": documented_type,
                "row_count": row_count,
                "raw_null_count": raw_null_count,
                "whitespace_only_count": whitespace_only_count,
                "normalized_null_count": normalized_null_count,
                "null_percent": null_percent,
                "non_null_count": non_null_count,
                "distinct_non_null": distinct_non_null,
                "uniqueness_percent_non_null": uniqueness_percent,
                "complete_and_unique_single_column": (
                    "yes" if complete_and_unique else "no"
                ),
                "sample_values_local_only": format_sample_values(
                    non_null_series
                ),
            }
        )

    return profile_rows


def main() -> None:
    """Run file-level and column-level profiling."""

    missing_files = [
        file_name
        for file_name in SOURCE_SPECS
        if not (SOURCE_DIRECTORY / file_name).is_file()
    ]

    if missing_files:
        raise FileNotFoundError(
            "Missing expected source files: "
            + ", ".join(missing_files)
        )

    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    inventory_rows = []
    column_profile_rows = []

    for file_name, source_spec in SOURCE_SPECS.items():
        file_path = SOURCE_DIRECTORY / file_name

        print(f"Reading {file_name}...")

        dataframe = load_source_file(file_path)

        normalized_dataframe = pd.DataFrame(
            {
                column_name: normalize_column(dataframe[column_name])
                for column_name in dataframe.columns
            }
        )

        inventory_rows.append(
            build_inventory_row(
                file_path=file_path,
                dataframe=dataframe,
                source_spec=source_spec,
                normalized_dataframe=normalized_dataframe,
            )
        )

        column_profile_rows.extend(
            build_column_profile_rows(
                file_name=file_name,
                dataframe=dataframe,
                normalized_dataframe=normalized_dataframe,
                source_spec=source_spec,
            )
        )

    inventory_report = pd.DataFrame(inventory_rows)
    column_profile_report = pd.DataFrame(column_profile_rows)

    inventory_output = REPORT_DIRECTORY / "source_inventory.csv"
    column_output = REPORT_DIRECTORY / "column_profile.csv"

    inventory_report.to_csv(inventory_output, index=False)
    column_profile_report.to_csv(column_output, index=False)

    console_columns = [
        "file_name",
        "requirements_row_count",
        "actual_row_count",
        "row_count_matches_requirement",
        "column_count",
        "duplicate_rows_after_first",
        "normalized_duplicate_rows_after_first",
        "missing_expected_columns",
        "unexpected_columns",
    ]

    print("\nSOURCE INVENTORY")
    print(
        inventory_report[console_columns].to_string(index=False)
    )

    print("\nREPORTS WRITTEN")
    print(inventory_output)
    print(column_output)


if __name__ == "__main__":
    main()