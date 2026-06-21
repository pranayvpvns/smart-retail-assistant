import pandas as pd
import numpy as np


def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Cleans the ingested DataFrame.

    Steps:
      1. Standardize date format to YYYY-MM-DD
      2. Impute missing numeric values with column median
      3. Drop rows missing critical identifier fields
      4. Cast numeric columns safely
      5. Strip whitespace from string fields

    Returns:
        cleaned_df  — the cleaned DataFrame
        report      — dict summarizing what was changed
    """

    report = {
        "rows_before": len(df),
        "duplicates_removed": 0,
        "nulls_imputed": 0,
        "invalid_rows_dropped": 0,
        "rows_after": 0,
    }

    df = df.copy()

    # ─────────────────────────────────────────────
    # 1. Standardize Dates (YYYY-MM-DD ONLY)
    # ─────────────────────────────────────────────
    df["date"] = (
        df["date"]
        .astype(str)
        .str.strip()
    )

    df["date"] = pd.to_datetime(
        df["date"],
        format="%Y-%m-%d",
        errors="coerce"
    )

    invalid_dates = df["date"].isnull().sum()

    if invalid_dates > 0:
        print(f"⚠️ Dropping {invalid_dates} invalid date rows")

    df = df.dropna(subset=["date"])

    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    # ─────────────────────────────────────────────
    # 2. Drop Rows Missing Critical Fields
    # ─────────────────────────────────────────────
    critical_cols = ["date", "product_id", "product_name"]

    before_drop = len(df)

    df = df.dropna(subset=critical_cols)

    report["invalid_rows_dropped"] = before_drop - len(df)

    # ─────────────────────────────────────────────
    # 3. Impute Numeric Columns
    # ─────────────────────────────────────────────
    numeric_cols = [
        "quantity_sold",
        "revenue",
        "cost",
        "stock_level"
    ]

    nulls_imputed = 0

    for col in numeric_cols:
        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

            null_count = df[col].isnull().sum()

            if null_count > 0:
                median_val = df[col].median()
                df[col] = df[col].fillna(median_val)
                nulls_imputed += null_count

    report["nulls_imputed"] = int(nulls_imputed)

    # ─────────────────────────────────────────────
    # 4. Cast Numeric Types
    # ─────────────────────────────────────────────
    for col in ["quantity_sold", "stock_level"]:
        if col in df.columns:
            df[col] = df[col].astype(int)

    for col in ["revenue", "cost"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    # ─────────────────────────────────────────────
    # 5. Skip Duplicate Removal
    # ─────────────────────────────────────────────
    # Retail datasets can contain multiple valid
    # transactions for same product/date/store.
    report["duplicates_removed"] = 0

    # ─────────────────────────────────────────────
    # 6. Clean String Columns
    # ─────────────────────────────────────────────
    str_cols = [
        "product_id",
        "product_name",
        "store_id",
        "category"
    ]

    for col in str_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
            )

    report["rows_after"] = len(df)

    return df, report