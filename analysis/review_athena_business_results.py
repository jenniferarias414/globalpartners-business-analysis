"""Print a concise review of the downloaded Athena business-query results."""

from pathlib import Path

import pandas as pd


RESULT_DIRECTORY = Path("reports/generated/athena-business")


def read_result(file_name: str) -> pd.DataFrame:
    """Read one Athena result and fail clearly if it is unavailable."""
    path = RESULT_DIRECTORY / file_name
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run scripts/run_athena_business_queries.sh first."
        )
    return pd.read_csv(path)


def print_section(title: str, dataframe: pd.DataFrame) -> None:
    """Print one labeled result section without a pandas row index."""
    print(f"\n{title}")
    print("-" * len(title))
    print(dataframe.to_string(index=False))


def main() -> None:
    """Load the eight Athena outputs and print their important values."""
    clv_tiers = read_result("02_clv_tier_summary.csv")
    print_section("CLV TIER SUMMARY", clv_tiers)

    top_customers = read_result("03_top_customers_by_clv.csv")
    print_section(
        "TOP 10 CUSTOMERS BY LIFETIME REVENUE",
        top_customers[
            [
                "user_id",
                "clv_tier",
                "customer_segment",
                "churn_status",
                "lifetime_order_count",
                "lifetime_revenue",
                "average_order_value",
                "days_since_last_order",
            ]
        ].head(10),
    )

    clv_evolution = read_result("04_customer_clv_evolution.csv")
    first_clv_row = clv_evolution.iloc[0]
    last_clv_row = clv_evolution.iloc[-1]
    clv_evolution_summary = pd.DataFrame(
        [
            {
                "user_id": last_clv_row["user_id"],
                "active_order_dates": len(clv_evolution),
                "first_order_date": first_clv_row["order_date"],
                "latest_order_date": last_clv_row["order_date"],
                "final_cumulative_orders": last_clv_row[
                    "cumulative_order_count"
                ],
                "final_customer_lifetime_value": last_clv_row[
                    "customer_lifetime_value"
                ],
            }
        ]
    )
    print_section("TOP CUSTOMER CLV EVOLUTION", clv_evolution_summary)

    rfm_segments = read_result("05_rfm_segments_and_churn.csv")
    print_section("RFM SEGMENTS AND CHURN", rfm_segments)

    monthly_sales = read_result("06_monthly_sales_trends.csv")
    monthly_sales["month"] = (
        monthly_sales["order_year"].astype(str)
        + "-"
        + monthly_sales["order_month"].astype(str).str.zfill(2)
    )
    monthly_summary = pd.DataFrame(
        [
            {
                "first_month": monthly_sales.iloc[0]["month"],
                "last_month": monthly_sales.iloc[-1]["month"],
                "months_present": len(monthly_sales),
                "total_orders": monthly_sales["order_count"].sum(),
                "total_revenue": round(monthly_sales["total_revenue"].sum(), 2),
            }
        ]
    )
    print_section("MONTHLY SALES COVERAGE", monthly_summary)
    print_section(
        "MOST RECENT 12 MONTHLY RESULTS",
        monthly_sales[
            [
                "month",
                "order_count",
                "item_revenue",
                "option_revenue",
                "total_revenue",
                "average_order_value",
            ]
        ].tail(12),
    )

    loyalty = read_result("07_loyalty_performance.csv")
    print_section("LOYALTY PERFORMANCE", loyalty)

    locations = read_result("08_location_performance.csv")
    print_section("TOP 10 LOCATIONS BY REVENUE", locations.head(10))

    discount = read_result("09_discount_data_availability.csv")
    print_section("DISCOUNT DATA AVAILABILITY", discount)


if __name__ == "__main__":
    main()
