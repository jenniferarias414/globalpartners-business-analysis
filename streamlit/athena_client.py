import os
import time

import boto3
import pandas as pd
import streamlit as st


REGION = os.getenv("AWS_REGION", "us-east-2")
PROFILE = os.getenv("AWS_PROFILE")
WORKGROUP = os.getenv("GP_ATHENA_WORKGROUP", "globalpartners-analysis")


@st.cache_resource
def athena_client():
    if PROFILE:
        session = boto3.Session(
            profile_name=PROFILE,
            region_name=REGION,
        )
    else:
        # EC2 uses its attached IAM instance role instead of a local profile.
        session = boto3.Session(region_name=REGION)
    return session.client("athena")


@st.cache_data(ttl=900, show_spinner="Querying Athena...")
def run_query(sql: str, timeout_seconds: int = 180) -> pd.DataFrame:
    client = athena_client()
    execution = client.start_query_execution(
        QueryString=sql,
        WorkGroup=WORKGROUP,
    )
    query_id = execution["QueryExecutionId"]
    deadline = time.monotonic() + timeout_seconds

    while True:
        details = client.get_query_execution(QueryExecutionId=query_id)
        state = details["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in {"FAILED", "CANCELLED"}:
            reason = details["QueryExecution"]["Status"].get("StateChangeReason", "Unknown error")
            raise RuntimeError(f"Athena query {state.lower()}: {reason}")
        if time.monotonic() >= deadline:
            client.stop_query_execution(QueryExecutionId=query_id)
            raise RuntimeError(
                f"Athena query exceeded {timeout_seconds} seconds and was stopped."
            )
        time.sleep(0.75)

    paginator = client.get_paginator("get_query_results")
    rows = []
    column_names = None
    for page in paginator.paginate(QueryExecutionId=query_id):
        if column_names is None:
            column_names = [
                column["Name"]
                for column in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            ]
        rows.extend(page["ResultSet"]["Rows"])

    if not rows or not column_names:
        return pd.DataFrame(columns=column_names or [])

    values = [
        [cell.get("VarCharValue") for cell in row.get("Data", [])]
        for row in rows[1:]
    ]
    frame = pd.DataFrame(values, columns=column_names)

    numeric_columns = {
        "total_revenue",
        "total_orders",
        "units_sold",
        "average_order_value",
        "identified_customers",
        "at_risk_customers",
        "average_customer_value",
        "active_customers",
        "average_lifetime_orders",
        "customer_count",
        "average_lifetime_revenue",
        "total_lifetime_revenue",
        "average_days_since_last_order",
        "lifetime_order_count",
        "lifetime_revenue",
        "days_since_last_order",
        "order_count",
        "identified_customer_orders",
        "identified_customer_count",
        "total_locations",
        "average_revenue_per_location",
        "active_sales_days",
        "loyalty_order_percent",
        "revenue",
        "orders",
    }
    for column in numeric_columns.intersection(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "order_month" in frame.columns:
        frame["order_month"] = pd.to_datetime(frame["order_month"])
    return frame
