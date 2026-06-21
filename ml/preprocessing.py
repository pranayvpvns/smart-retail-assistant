import sys
import os

ROOT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

sys.path.insert(0, ROOT_DIR)

import pandas as pd
import numpy as np

from pymongo.database import Database


# ─────────────────────────────────────────────
# Load Sales Data
# ─────────────────────────────────────────────
def load_sales_from_mongo(
    db: Database,
    store_id: str
) -> pd.DataFrame:
    """
    Loads all sales records for a store
    from MongoDB into a pandas DataFrame.
    """

    records = list(
        db["sales_records"].find(
            {"store_id": store_id},
            {"_id": 0},
        )
    )

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce"
    )

    df = df.dropna(subset=["date"])

    df = df.sort_values(
        ["product_id", "date"]
    ).reset_index(drop=True)

    return df


# ─────────────────────────────────────────────
# Season Encoder
# ─────────────────────────────────────────────
def encode_season(month: int) -> int:
    """
    Encodes month into seasonal category.

    Winter  → 0
    Summer  → 1
    Monsoon → 2
    Festive → 3
    """

    if month in [12, 1, 2]:
        return 0

    elif month in [3, 4, 5, 6]:
        return 1

    elif month in [7, 8, 9]:
        return 2

    return 3


# ─────────────────────────────────────────────
# Holiday Flag Generator
# ─────────────────────────────────────────────
def is_holiday(date: pd.Timestamp) -> int:
    """
    Simple holiday approximation.

    Marks:
    - Sundays
    - Major festive dates

    as holidays.
    """

    # Sundays
    if date.weekday() == 6:
        return 1

    # Example festive dates
    festive_dates = [
        "2026-01-01",
        "2026-10-24",
        "2026-12-25",
    ]

    if str(date.date()) in festive_dates:
        return 1

    return 0


# ─────────────────────────────────────────────
# Prophet Dataset Builder
# ─────────────────────────────────────────────
def build_prophet_dataframe(
    df: pd.DataFrame,
    product_id: str
) -> pd.DataFrame:
    """
    Creates Prophet-ready dataframe
    with external regressors.

    Features added:
    - is_weekend
    - is_holiday
    - season_encoded
    """

    product_df = df[
        df["product_id"] == product_id
    ].copy()

    product_df = product_df.rename(
        columns={
            "date": "ds",
            "quantity_sold": "y"
        }
    )

    product_df = product_df.sort_values(
        "ds"
    ).reset_index(drop=True)

    # Prophet cannot handle negatives
    product_df["y"] = (
        product_df["y"]
        .clip(lower=0)
    )

    # ─────────────────────────────────────────
    # Feature Engineering
    # ─────────────────────────────────────────

    # Weekend feature
    product_df["is_weekend"] = (
        pd.to_datetime(product_df["ds"])
        .dt.dayofweek
        .isin([5, 6])
        .astype(int)
    )

    # Holiday feature
    product_df["is_holiday"] = (
        pd.to_datetime(product_df["ds"])
        .apply(is_holiday)
    )

    # Seasonal feature
    product_df["season_encoded"] = (
        pd.to_datetime(product_df["ds"])
        .dt.month
        .apply(encode_season)
    )

    # Keep only required columns
    product_df = product_df[
        [
            "ds",
            "y",
            "is_weekend",
            "is_holiday",
            "season_encoded",
        ]
    ]

    return product_df


# ─────────────────────────────────────────────
# Anomaly Feature Engineering
# ─────────────────────────────────────────────
def build_anomaly_features(
    df: pd.DataFrame,
    product_id: str
) -> pd.DataFrame:
    """
    Engineers features for
    IsolationForest anomaly detection.
    """

    product_df = df[
        df["product_id"] == product_id
    ].copy()

    product_df = product_df.sort_values(
        "date"
    ).reset_index(drop=True)

    # Rolling statistics
    product_df["rolling_mean_7"] = (
        product_df["quantity_sold"]
        .rolling(window=7, min_periods=1)
        .mean()
    )

    product_df["rolling_std_7"] = (
        product_df["quantity_sold"]
        .rolling(window=7, min_periods=1)
        .std()
        .fillna(0)
    )

    # Lag features
    product_df["lag_1"] = (
        product_df["quantity_sold"]
        .shift(1)
        .fillna(0)
    )

    product_df["lag_7"] = (
        product_df["quantity_sold"]
        .shift(7)
        .fillna(0)
    )

    # Day of week
    product_df["day_of_week"] = (
        pd.to_datetime(product_df["date"])
        .dt.dayofweek
    )

    # Weekend feature
    product_df["is_weekend"] = (
        pd.to_datetime(product_df["date"])
        .dt.dayofweek
        .isin([5, 6])
        .astype(int)
    )

    # Holiday feature
    product_df["is_holiday"] = (
        pd.to_datetime(product_df["date"])
        .apply(is_holiday)
    )

    # Season feature
    product_df["season_encoded"] = (
        pd.to_datetime(product_df["date"])
        .dt.month
        .apply(encode_season)
    )

    feature_cols = [
        "quantity_sold",
        "revenue",
        "rolling_mean_7",
        "rolling_std_7",
        "lag_1",
        "lag_7",
        "day_of_week",
        "is_weekend",
        "is_holiday",
        "season_encoded",
    ]

    available = [
        c for c in feature_cols
        if c in product_df.columns
    ]

    return product_df[
        ["date", "product_id"] + available
    ].dropna()


# ─────────────────────────────────────────────
# Unique Product Fetcher
# ─────────────────────────────────────────────
def get_unique_products(
    df: pd.DataFrame
) -> list[str]:
    """
    Returns sorted unique product IDs.
    """

    return sorted(
        df["product_id"]
        .unique()
        .tolist()
    )