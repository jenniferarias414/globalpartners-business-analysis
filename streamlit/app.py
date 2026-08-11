"""GlobalPartners Streamlit dashboard backed by Athena Gold tables."""

import os

import altair as alt
import streamlit as st

from athena_client import run_query


st.set_page_config(
    page_title="GlobalPartners Business Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("GlobalPartners Business Dashboard")
st.caption("Business performance and customer analysis powered by AWS Athena Gold tables")

with st.sidebar:
    st.header("Dashboard Controls")
    if st.button("Refresh Athena data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("Data source")
    st.write("Amazon Athena")
    st.code(os.getenv("GP_GLUE_DATABASE", "globalpartners_gold"))
    st.caption("Results are cached for 15 minutes to limit repeated queries and cost.")

LATEST_ORDERS = """
SELECT *
FROM globalpartners_gold.fact_order
WHERE load_date = (
    SELECT MAX(load_date)
    FROM globalpartners_gold.fact_order
)
"""

LATEST_CUSTOMERS = """
SELECT *
FROM globalpartners_gold.customer_profile
WHERE load_date = (
    SELECT MAX(load_date)
    FROM globalpartners_gold.customer_profile
)
"""

overview = run_query(
    f"""
    WITH current_orders AS ({LATEST_ORDERS})
    SELECT
        CAST(SUM(order_revenue) AS DOUBLE) AS total_revenue,
        COUNT(*) AS total_orders,
        SUM(item_quantity) AS units_sold,
        CAST(AVG(order_revenue) AS DOUBLE) AS average_order_value,
        MIN(order_date) AS first_order_date,
        MAX(order_date) AS last_order_date
    FROM current_orders
    """
).iloc[0]

customer_summary = run_query(
    f"""
    WITH current_customers AS ({LATEST_CUSTOMERS})
    SELECT
        COUNT(*) AS identified_customers,
        COUNT_IF(churn_status = 'AT_RISK') AS at_risk_customers,
        COUNT_IF(churn_status = 'ACTIVE') AS active_customers,
        CAST(AVG(lifetime_revenue) AS DOUBLE) AS average_customer_value,
        CAST(AVG(lifetime_order_count) AS DOUBLE) AS average_lifetime_orders
    FROM current_customers
    """
).iloc[0]

monthly = run_query(
    f"""
    WITH current_orders AS ({LATEST_ORDERS})
    SELECT
        DATE_TRUNC('month', order_date) AS order_month,
        CAST(SUM(order_revenue) AS DOUBLE) AS revenue,
        COUNT(*) AS orders
    FROM current_orders
    GROUP BY 1
    ORDER BY 1
    """
).set_index("order_month")

clv_tiers = run_query(
    f"""
    WITH current_customers AS ({LATEST_CUSTOMERS})
    SELECT
        clv_tier,
        COUNT(*) AS customer_count,
        CAST(AVG(lifetime_revenue) AS DOUBLE) AS average_lifetime_revenue,
        CAST(SUM(lifetime_revenue) AS DOUBLE) AS total_lifetime_revenue
    FROM current_customers
    GROUP BY clv_tier
    ORDER BY CASE clv_tier
        WHEN 'HIGH' THEN 1
        WHEN 'MEDIUM' THEN 2
        WHEN 'LOW' THEN 3
        ELSE 4
    END
    """
)

customer_segments = run_query(
    f"""
    WITH current_customers AS ({LATEST_CUSTOMERS})
    SELECT
        customer_segment,
        COUNT(*) AS customer_count,
        CAST(AVG(days_since_last_order) AS DOUBLE)
            AS average_days_since_last_order,
        CAST(SUM(lifetime_revenue) AS DOUBLE) AS total_lifetime_revenue
    FROM current_customers
    GROUP BY customer_segment
    ORDER BY customer_count DESC
    """
)

top_customers = run_query(
    f"""
    WITH current_customers AS ({LATEST_CUSTOMERS})
    SELECT
        user_id,
        lifetime_order_count,
        CAST(lifetime_revenue AS DOUBLE) AS lifetime_revenue,
        CAST(average_order_value AS DOUBLE) AS average_order_value,
        clv_tier,
        customer_segment,
        churn_status,
        days_since_last_order
    FROM current_customers
    ORDER BY lifetime_revenue DESC
    LIMIT 10
    """
)

loyalty = run_query(
    f"""
    WITH current_orders AS ({LATEST_ORDERS})
    SELECT
        CASE
            WHEN is_loyalty THEN 'Loyalty'
            ELSE 'Non-Loyalty'
        END AS order_type,
        COUNT(*) AS order_count,
        CAST(SUM(order_revenue) AS DOUBLE) AS total_revenue,
        CAST(AVG(order_revenue) AS DOUBLE) AS average_order_value,
        COUNT_IF(has_identified_customer) AS identified_customer_orders
    FROM current_orders
    GROUP BY is_loyalty
    ORDER BY order_type
    """
)

sales_channels = run_query(
    f"""
    WITH current_orders AS ({LATEST_ORDERS})
    SELECT
        app_name,
        COUNT(*) AS order_count,
        CAST(SUM(order_revenue) AS DOUBLE) AS total_revenue,
        CAST(AVG(order_revenue) AS DOUBLE) AS average_order_value,
        COUNT(DISTINCT user_id) AS identified_customer_count
    FROM current_orders
    GROUP BY app_name
    ORDER BY total_revenue DESC
    """
)

location_summary = run_query(
    f"""
    WITH current_orders AS ({LATEST_ORDERS})
    SELECT
        COUNT(DISTINCT restaurant_id) AS total_locations,
        CAST(
            SUM(order_revenue) / COUNT(DISTINCT restaurant_id)
            AS DOUBLE
        ) AS average_revenue_per_location
    FROM current_orders
    """
).iloc[0]

locations = run_query(
    f"""
    WITH current_orders AS ({LATEST_ORDERS})
    SELECT
        restaurant_id,
        COUNT(*) AS order_count,
        COUNT(DISTINCT order_date) AS active_sales_days,
        CAST(SUM(order_revenue) AS DOUBLE) AS total_revenue,
        CAST(AVG(order_revenue) AS DOUBLE) AS average_order_value,
        COUNT(DISTINCT user_id) AS identified_customer_count,
        CAST(100.0 * COUNT_IF(is_loyalty) / COUNT(*) AS DOUBLE)
            AS loyalty_order_percent
    FROM current_orders
    GROUP BY restaurant_id
    ORDER BY total_revenue DESC
    LIMIT 15
    """
)


def short_identifier(value: object) -> str:
    """Create a readable chart label while preserving full IDs in tables."""

    identifier = str(value)
    if len(identifier) <= 18:
        return identifier
    return f"{identifier[:8]}…{identifier[-5:]}"


locations["location_label"] = locations["restaurant_id"].apply(
    short_identifier
)

loyalty_summary = loyalty.set_index("order_type")
loyalty_orders = loyalty_summary.loc["Loyalty", "order_count"]
loyalty_revenue = loyalty_summary.loc["Loyalty", "total_revenue"]
loyalty_order_share = 100 * loyalty_orders / overview["total_orders"]
loyalty_revenue_share = 100 * loyalty_revenue / overview["total_revenue"]

overview_tab, customer_tab, sales_tab, location_tab = st.tabs(
    [
        "Executive Overview",
        "Customer and CLV",
        "Sales and Loyalty",
        "Location Performance",
    ]
)

with overview_tab:
    cols = st.columns(4)
    cols[0].metric("Total Revenue", f"${overview['total_revenue']:,.2f}")
    cols[1].metric("Orders", f"{int(overview['total_orders']):,}")
    cols[2].metric(
        "Average Order Value",
        f"${overview['average_order_value']:,.2f}",
    )
    cols[3].metric(
        "Identified Customers",
        f"{int(customer_summary['identified_customers']):,}",
    )

    st.caption(
        f"Order history: {overview['first_order_date']} through "
        f"{overview['last_order_date']} · "
        f"Units sold: {int(overview['units_sold']):,} · "
        "Average identified-customer value: "
        f"${customer_summary['average_customer_value']:,.2f}"
    )

    st.subheader("Monthly Revenue and Orders")
    revenue_column, orders_column = st.columns(2)
    with revenue_column:
        st.caption("Monthly revenue")
        st.line_chart(monthly[["revenue"]], height=340)
    with orders_column:
        st.caption("Monthly orders")
        st.line_chart(monthly[["orders"]], height=340)

    with st.expander("Dashboard data notes"):
        st.markdown(
            """
            - Revenue includes item and option revenue.
            - Overall sales include orders without a `user_id`.
            - Customer metrics include only identified customers.
            - Profit and discount metrics are excluded because source cost and explicit discount fields were not supplied.
            """
        )

with customer_tab:
    st.subheader("Customer and Lifetime Value Summary")
    customer_cols = st.columns(4)
    customer_cols[0].metric(
        "Identified Customers",
        f"{int(customer_summary['identified_customers']):,}",
    )
    customer_cols[1].metric(
        "At-Risk Customers",
        f"{int(customer_summary['at_risk_customers']):,}",
    )
    customer_cols[2].metric(
        "Average Lifetime Value",
        f"${customer_summary['average_customer_value']:,.2f}",
    )
    customer_cols[3].metric(
        "Average Lifetime Orders",
        f"{customer_summary['average_lifetime_orders']:,.2f}",
    )

    clv_column, segment_column = st.columns(2)
    with clv_column:
        st.subheader("Customers by CLV Tier")
        clv_chart = (
            alt.Chart(clv_tiers)
            .mark_bar(color="#59A9E6")
            .encode(
                x=alt.X(
                    "clv_tier:N",
                    title="CLV Tier",
                    sort=["HIGH", "MEDIUM", "LOW"],
                ),
                y=alt.Y("customer_count:Q", title="Customers"),
                tooltip=[
                    alt.Tooltip("clv_tier:N", title="CLV Tier"),
                    alt.Tooltip(
                        "customer_count:Q",
                        title="Customers",
                        format=",",
                    ),
                ],
            )
        )
        st.altair_chart(
            clv_chart.properties(height=340),
            use_container_width=True,
        )
    with segment_column:
        st.subheader("Customers by RFM Segment")
        segment_chart_data = customer_segments.copy()
        segment_chart_data["segment_label"] = segment_chart_data[
            "customer_segment"
        ].replace(
            {
                "CHURN_RISK": "Churn Risk",
                "NEW_CUSTOMER": "New Customer",
                "OTHER_ACTIVE": "Other Active",
                "VIP": "VIP",
            }
        )
        segment_chart = (
            alt.Chart(segment_chart_data)
            .mark_bar(color="#59A9E6")
            .encode(
                x=alt.X(
                    "segment_label:N",
                    title="RFM Segment",
                    sort="-y",
                ),
                y=alt.Y("customer_count:Q", title="Customers"),
                tooltip=[
                    alt.Tooltip("segment_label:N", title="Segment"),
                    alt.Tooltip(
                        "customer_count:Q",
                        title="Customers",
                        format=",",
                    ),
                ],
            )
        )
        st.altair_chart(
            segment_chart.properties(height=340),
            use_container_width=True,
        )

    st.subheader("CLV Tier Detail")
    clv_display = clv_tiers.rename(
        columns={
            "clv_tier": "CLV Tier",
            "customer_count": "Customers",
            "average_lifetime_revenue": "Average Lifetime Revenue",
            "total_lifetime_revenue": "Total Lifetime Revenue",
        }
    )
    st.dataframe(
        clv_display.style.format(
            {
                "Customers": "{:,.0f}",
                "Average Lifetime Revenue": "${:,.2f}",
                "Total Lifetime Revenue": "${:,.2f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Top 10 Customers by Lifetime Revenue")
    top_customer_display = top_customers.rename(
        columns={
            "user_id": "Customer ID",
            "lifetime_order_count": "Lifetime Orders",
            "lifetime_revenue": "Lifetime Revenue",
            "average_order_value": "Average Order Value",
            "clv_tier": "CLV Tier",
            "customer_segment": "RFM Segment",
            "churn_status": "Churn Status",
            "days_since_last_order": "Days Since Last Order",
        }
    )
    st.dataframe(
        top_customer_display.style.format(
            {
                "Lifetime Orders": "{:,.0f}",
                "Lifetime Revenue": "${:,.2f}",
                "Average Order Value": "${:,.2f}",
                "Days Since Last Order": "{:,.0f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Customer metric definitions"):
        st.markdown(
            """
            - **Lifetime value:** Total revenue from an identified customer's accepted orders.
            - **CLV tier:** HIGH, MEDIUM, or LOW based on customer lifetime-revenue ranking.
            - **RFM segment:** Customer grouping based on recency, frequency, and monetary value.
            - **At risk:** No order within 45 days of the latest order date in the dataset.
            - Customers without a `user_id` remain in overall sales but are excluded from customer-level analysis.
            """
        )

with sales_tab:
    st.subheader("Sales and Loyalty Summary")
    sales_cols = st.columns(4)
    sales_cols[0].metric("Total Revenue", f"${overview['total_revenue']:,.2f}")
    sales_cols[1].metric("Total Orders", f"{int(overview['total_orders']):,}")
    sales_cols[2].metric("Loyalty Order Share", f"{loyalty_order_share:.2f}%")
    sales_cols[3].metric(
        "Loyalty Revenue Share",
        f"{loyalty_revenue_share:.2f}%",
    )

    st.subheader("Monthly Sales Trends")
    monthly_revenue, monthly_orders = st.columns(2)
    with monthly_revenue:
        st.caption("Monthly revenue")
        st.line_chart(monthly[["revenue"]], height=340)
    with monthly_orders:
        st.caption("Monthly orders")
        st.line_chart(monthly[["orders"]], height=340)

    loyalty_column, channel_column = st.columns(2)
    with loyalty_column:
        st.subheader("Revenue by Loyalty Status")
        loyalty_chart = (
            alt.Chart(loyalty)
            .mark_bar(color="#59A9E6")
            .encode(
                x=alt.X("order_type:N", title="Order Type"),
                y=alt.Y("total_revenue:Q", title="Revenue"),
                tooltip=[
                    alt.Tooltip("order_type:N", title="Order Type"),
                    alt.Tooltip(
                        "total_revenue:Q",
                        title="Revenue",
                        format="$,.2f",
                    ),
                ],
            )
        )
        st.altair_chart(
            loyalty_chart.properties(height=340),
            use_container_width=True,
        )
    with channel_column:
        st.subheader("Revenue by Sales Channel")
        channel_chart = (
            alt.Chart(sales_channels)
            .mark_bar(color="#59A9E6")
            .encode(
                x=alt.X("total_revenue:Q", title="Revenue"),
                y=alt.Y("app_name:N", title="Sales Channel", sort="-x"),
                tooltip=[
                    alt.Tooltip("app_name:N", title="Sales Channel"),
                    alt.Tooltip(
                        "total_revenue:Q",
                        title="Revenue",
                        format="$,.2f",
                    ),
                ],
            )
        )
        st.altair_chart(
            channel_chart.properties(height=340),
            use_container_width=True,
        )

    st.subheader("Loyalty Performance Detail")
    loyalty_display = loyalty.rename(
        columns={
            "order_type": "Order Type",
            "order_count": "Orders",
            "total_revenue": "Revenue",
            "average_order_value": "Average Order Value",
            "identified_customer_orders": "Identified-Customer Orders",
        }
    )
    st.dataframe(
        loyalty_display.style.format(
            {
                "Orders": "{:,.0f}",
                "Revenue": "${:,.2f}",
                "Average Order Value": "${:,.2f}",
                "Identified-Customer Orders": "{:,.0f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Sales Channel Detail")
    channel_display = sales_channels.rename(
        columns={
            "app_name": "Sales Channel",
            "order_count": "Orders",
            "total_revenue": "Revenue",
            "average_order_value": "Average Order Value",
            "identified_customer_count": "Identified Customers",
        }
    )
    st.dataframe(
        channel_display.style.format(
            {
                "Orders": "{:,.0f}",
                "Revenue": "${:,.2f}",
                "Average Order Value": "${:,.2f}",
                "Identified Customers": "{:,.0f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Sales and loyalty definitions"):
        st.markdown(
            """
            - **Loyalty order share:** Percentage of accepted orders flagged as loyalty transactions.
            - **Loyalty revenue share:** Percentage of total accepted revenue generated by loyalty orders.
            - **Sales channel:** Source application recorded in `app_name`.
            - Revenue includes both item and option revenue.
            """
        )

with location_tab:
    top_location = locations.iloc[0]

    st.subheader("Location Performance Summary")
    location_cols = st.columns(4)
    location_cols[0].metric(
        "Locations",
        f"{int(location_summary['total_locations']):,}",
    )
    location_cols[1].metric(
        "Top Location",
        short_identifier(top_location["restaurant_id"]),
    )
    location_cols[2].metric(
        "Top Location Revenue",
        f"${top_location['total_revenue']:,.2f}",
    )
    location_cols[3].metric(
        "Average Revenue per Location",
        f"${location_summary['average_revenue_per_location']:,.2f}",
    )

    st.subheader("Top 15 Locations by Revenue")
    location_chart = (
        alt.Chart(locations)
        .mark_bar(color="#59A9E6")
        .encode(
            x=alt.X("total_revenue:Q", title="Revenue"),
            y=alt.Y("location_label:N", title="Location ID", sort="-x"),
            tooltip=[
                alt.Tooltip("restaurant_id:N", title="Location ID"),
                alt.Tooltip(
                    "total_revenue:Q",
                    title="Revenue",
                    format="$,.2f",
                ),
                alt.Tooltip("order_count:Q", title="Orders", format=","),
            ],
        )
    )
    st.altair_chart(
        location_chart.properties(height=500),
        use_container_width=True,
    )

    st.subheader("Location Performance Detail")
    location_display = locations.rename(
        columns={
            "restaurant_id": "Location ID",
            "order_count": "Orders",
            "active_sales_days": "Active Sales Days",
            "total_revenue": "Revenue",
            "average_order_value": "Average Order Value",
            "identified_customer_count": "Identified Customers",
            "loyalty_order_percent": "Loyalty Order Share",
        }
    )
    st.dataframe(
        location_display.style.format(
            {
                "Orders": "{:,.0f}",
                "Active Sales Days": "{:,.0f}",
                "Revenue": "${:,.2f}",
                "Average Order Value": "${:,.2f}",
                "Identified Customers": "{:,.0f}",
                "Loyalty Order Share": "{:.2f}%",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Location metric definitions"):
        st.markdown(
            """
            - **Location:** Source `restaurant_id`, used as the requested location identifier.
            - **Active sales days:** Distinct order dates represented for the location.
            - **Average revenue per location:** Total accepted revenue divided by the number of represented locations.
            - **Loyalty order share:** Percentage of the location's accepted orders flagged as loyalty transactions.
            """
        )
