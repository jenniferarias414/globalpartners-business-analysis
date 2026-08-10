"""Test how item and option prices behave before defining Gold revenue."""

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "project-assets" / "source-downloads"
REPORT_DIR = PROJECT_ROOT / "reports" / "generated"

ORDER_ITEMS_PATH = SOURCE_DIR / "order_items.csv"
OPTIONS_PATH = SOURCE_DIR / "order_item_options.csv"


def read_source(path: Path) -> pd.DataFrame:
    """Read a source CSV and standardize its column names."""
    dataframe = pd.read_csv(path, low_memory=False)
    dataframe.columns = dataframe.columns.str.strip().str.lower()
    return dataframe


def validate_columns(
    dataframe: pd.DataFrame,
    expected_columns: set[str],
    source_name: str,
) -> None:
    """Stop if a required source column is unavailable."""
    missing_columns = sorted(expected_columns.difference(dataframe.columns))
    if missing_columns:
        raise ValueError(
            f"{source_name} is missing columns: {', '.join(missing_columns)}"
        )


def build_item_quantity_comparison(
    order_items: pd.DataFrame,
) -> pd.DataFrame:
    """Compare line amounts at quantity one with higher quantities."""
    usable = order_items.loc[
        order_items["item_name"].notna()
        & order_items["item_price"].notna()
        & order_items["item_quantity"].gt(0)
    ].copy()

    grouped = (
        usable.groupby(["item_name", "item_quantity"], dropna=False)
        .agg(
            rows=("item_price", "size"),
            median_item_price=("item_price", "median"),
            minimum_item_price=("item_price", "min"),
            maximum_item_price=("item_price", "max"),
        )
        .reset_index()
    )

    quantity_one = (
        grouped.loc[
            grouped["item_quantity"].eq(1),
            ["item_name", "rows", "median_item_price"],
        ]
        .rename(
            columns={
                "rows": "quantity_one_rows",
                "median_item_price": "quantity_one_median_price",
            }
        )
    )

    comparison = grouped.loc[grouped["item_quantity"].gt(1)].merge(
        quantity_one,
        on="item_name",
        how="inner",
        validate="many_to_one",
    )
    comparison["implied_unit_amount"] = (
        comparison["median_item_price"] / comparison["item_quantity"]
    )
    comparison["implied_unit_to_quantity_one_ratio"] = (
        comparison["implied_unit_amount"]
        / comparison["quantity_one_median_price"]
    )
    comparison["implied_unit_within_10_percent"] = comparison[
        "implied_unit_to_quantity_one_ratio"
    ].between(0.90, 1.10)

    return comparison.sort_values(
        ["rows", "item_name", "item_quantity"],
        ascending=[False, True, True],
    )


def build_summary(
    order_items: pd.DataFrame,
    options: pd.DataFrame,
    comparison: pd.DataFrame,
) -> pd.DataFrame:
    """Create the concise evidence used to choose a revenue formula."""
    comparison_sample = comparison.loc[
        comparison["quantity_one_rows"].ge(20)
        & comparison["rows"].ge(5)
        & comparison["quantity_one_median_price"].gt(0)
    ]

    comparison_group_count = len(comparison_sample)
    groups_with_consistent_unit_amount = int(
        comparison_sample["implied_unit_within_10_percent"].sum()
    )
    support_percent = (
        round(
            100
            * groups_with_consistent_unit_amount
            / comparison_group_count,
            2,
        )
        if comparison_group_count
        else None
    )

    metrics = [
        {
            "metric": "order_item_rows",
            "value": len(order_items),
            "meaning": "Total order-item source rows tested.",
        },
        {
            "metric": "rows_with_quantity_greater_than_one",
            "value": int(order_items["item_quantity"].gt(1).sum()),
            "meaning": "Rows that allow price-versus-quantity comparison.",
        },
        {
            "metric": "rows_with_non_positive_quantity",
            "value": int(order_items["item_quantity"].le(0).sum()),
            "meaning": "Rows that cannot represent a normal positive purchase quantity.",
        },
        {
            "metric": "qualified_item_quantity_comparison_groups",
            "value": comparison_group_count,
            "meaning": (
                "Item and quantity groups with at least 20 quantity-one rows "
                "and at least 5 higher-quantity rows."
            ),
        },
        {
            "metric": "groups_with_consistent_implied_unit_amount",
            "value": groups_with_consistent_unit_amount,
            "meaning": (
                "Qualified groups whose price divided by quantity is within "
                "10% of the same item's quantity-one median."
            ),
        },
        {
            "metric": "extended_line_amount_pattern_support_percent",
            "value": support_percent,
            "meaning": (
                "Higher values support item_price behaving like an extended "
                "line amount rather than a single-unit price."
            ),
        },
        {
            "metric": "negative_option_price_rows",
            "value": int(options["option_price"].lt(0).sum()),
            "meaning": "Rows that could support the documented discount logic.",
        },
        {
            "metric": "distinct_option_quantity_values",
            "value": int(options["option_quantity"].nunique(dropna=True)),
            "meaning": "Number of different option-quantity values supplied.",
        },
        {
            "metric": "minimum_option_quantity",
            "value": options["option_quantity"].min(),
            "meaning": "Smallest supplied option quantity.",
        },
        {
            "metric": "maximum_option_quantity",
            "value": options["option_quantity"].max(),
            "meaning": "Largest supplied option quantity.",
        },
    ]

    return pd.DataFrame(metrics)


def main() -> None:
    """Run the revenue-logic analysis and write reproducible reports."""
    print("Reading source files...")
    order_items = read_source(ORDER_ITEMS_PATH)
    options = read_source(OPTIONS_PATH)

    validate_columns(
        order_items,
        {"item_name", "item_price", "item_quantity"},
        "order_items.csv",
    )
    validate_columns(
        options,
        {"option_price", "option_quantity"},
        "order_item_options.csv",
    )

    order_items["item_price"] = pd.to_numeric(
        order_items["item_price"], errors="coerce"
    )
    order_items["item_quantity"] = pd.to_numeric(
        order_items["item_quantity"], errors="coerce"
    )
    options["option_price"] = pd.to_numeric(
        options["option_price"], errors="coerce"
    )
    options["option_quantity"] = pd.to_numeric(
        options["option_quantity"], errors="coerce"
    )

    comparison = build_item_quantity_comparison(order_items)
    summary = build_summary(order_items, options, comparison)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = REPORT_DIR / "revenue_logic_summary.csv"
    comparison_path = REPORT_DIR / "item_price_quantity_comparison.csv"

    summary.to_csv(summary_path, index=False)
    comparison.to_csv(comparison_path, index=False)

    display_columns = [
        "item_name",
        "item_quantity",
        "rows",
        "median_item_price",
        "quantity_one_median_price",
        "implied_unit_amount",
        "implied_unit_to_quantity_one_ratio",
    ]

    print("\nREVENUE LOGIC SUMMARY")
    print(summary[["metric", "value"]].to_string(index=False))

    print("\nCOMMON HIGHER-QUANTITY EXAMPLES")
    print(comparison[display_columns].head(20).to_string(index=False))

    print("\nREPORTS WRITTEN")
    print(summary_path)
    print(comparison_path)


if __name__ == "__main__":
    main()
