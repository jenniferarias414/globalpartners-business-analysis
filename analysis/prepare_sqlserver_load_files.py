from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = PROJECT_ROOT / "project-assets" / "source-downloads"
OUTPUT_DIRECTORY = PROJECT_ROOT / "project-assets" / "sqlserver-load-ready"

EXPECTED_ROW_COUNTS = {
    "date_dim.csv": 365,
    "order_items.csv": 203_519,
    "order_item_options.csv": 193_017,
}


def read_source_file(file_name: str) -> pd.DataFrame:
    """Read every source column as text to preserve identifiers."""
    file_path = SOURCE_DIRECTORY / file_name

    dataframe = pd.read_csv(
        file_path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    dataframe.columns = [
        column.strip().lower()
        for column in dataframe.columns
    ]

    expected_rows = EXPECTED_ROW_COUNTS[file_name]

    if len(dataframe) != expected_rows:
        raise ValueError(
            f"{file_name}: expected {expected_rows:,} rows, "
            f"but found {len(dataframe):,}"
        )

    return dataframe


def convert_boolean_to_bit(
    dataframe: pd.DataFrame,
    column_name: str,
    file_name: str,
) -> None:
    """Convert CSV TRUE/FALSE values to SQL Server BIT values 1/0."""
    normalized_values = (
        dataframe[column_name]
        .str.strip()
        .str.upper()
    )

    unexpected_values = sorted(
        set(normalized_values) - {"TRUE", "FALSE"}
    )

    if unexpected_values:
        raise ValueError(
            f"{file_name}.{column_name} contains unexpected values: "
            f"{unexpected_values}"
        )

    dataframe[column_name] = normalized_values.map(
        {
            "TRUE": "1",
            "FALSE": "0",
        }
    )


def write_load_ready_file(
    dataframe: pd.DataFrame,
    file_name: str,
) -> None:
    """Write a prepared copy without changing the original source file."""
    output_path = OUTPUT_DIRECTORY / file_name

    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8",
    )

    print(f"{file_name}: {len(dataframe):,} rows -> {output_path}")


def prepare_date_dimension() -> None:
    dataframe = read_source_file("date_dim.csv")

    dataframe["date_key"] = pd.to_datetime(
        dataframe["date_key"],
        format="%d-%m-%Y",
        errors="raise",
    ).dt.strftime("%Y-%m-%d")

    convert_boolean_to_bit(
        dataframe,
        "is_weekend",
        "date_dim.csv",
    )

    convert_boolean_to_bit(
        dataframe,
        "is_holiday",
        "date_dim.csv",
    )

    write_load_ready_file(dataframe, "date_dim.csv")


def prepare_order_items() -> None:
    dataframe = read_source_file("order_items.csv")

    timestamps = pd.to_datetime(
        dataframe["creation_time_utc"],
        format="ISO8601",
        utc=True,
        errors="raise",
    )

    dataframe["creation_time_utc"] = (
        timestamps
        .dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        .str.slice(0, 23)
    )

    convert_boolean_to_bit(
        dataframe,
        "is_loyalty",
        "order_items.csv",
    )

    write_load_ready_file(dataframe, "order_items.csv")


def prepare_order_item_options() -> None:
    dataframe = read_source_file("order_item_options.csv")

    write_load_ready_file(
        dataframe,
        "order_item_options.csv",
    )


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    print("Preparing SQL Server load files...")

    prepare_date_dimension()
    prepare_order_items()
    prepare_order_item_options()

    print("SQL Server load files are ready.")


if __name__ == "__main__":
    main()