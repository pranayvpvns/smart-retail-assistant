import pandas as pd


# ─────────────────────────────────────────────
# Season Encoder
# ─────────────────────────────────────────────
def encode_season(month: int) -> int:

    if month in [12, 1, 2]:
        return 0

    elif month in [3, 4, 5, 6]:
        return 1

    elif month in [7, 8, 9]:
        return 2

    return 3


# ─────────────────────────────────────────────
# Holiday Detector
# ─────────────────────────────────────────────
def is_holiday(date: pd.Timestamp) -> int:

    # Sundays
    if date.weekday() == 6:
        return 1

    festive_dates = [
        "2026-01-01",
        "2026-10-24",
        "2026-12-25",
    ]

    if str(date.date()) in festive_dates:
        return 1

    return 0


# ─────────────────────────────────────────────
# Transform to Time Series
# ─────────────────────────────────────────────
def transform_to_timeseries(
    df: pd.DataFrame
) -> pd.DataFrame:
    """
    Converts cleaned retail sales data into
    context-aware time-series format.

    Adds:
    - is_weekend
    - is_holiday
    - season_encoded
    """

    df = df.copy()

    # ─────────────────────────────────────────
    # Parse Dates
    # ─────────────────────────────────────────
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

    invalid_dates = df["date"].isna().sum()

    if invalid_dates > 0:

        print(
            f"⚠️ Dropping "
            f"{invalid_dates} invalid date rows"
        )

    df = df.dropna(subset=["date"])

    # ─────────────────────────────────────────
    # Feature Engineering
    # ─────────────────────────────────────────

    # Weekend feature
    df["is_weekend"] = (
        df["date"]
        .dt.dayofweek
        .isin([5, 6])
        .astype(int)
    )

    # Holiday feature
    df["is_holiday"] = (
        df["date"]
        .apply(is_holiday)
    )

    # Seasonal feature
    df["season_encoded"] = (
        df["date"]
        .dt.month
        .apply(encode_season)
    )

    # ─────────────────────────────────────────
    # Select Relevant Columns
    # ─────────────────────────────────────────
    base_cols = [
        "date",
        "product_id",
        "product_name",
        "store_id",
        "quantity_sold",
        "revenue",
        "is_weekend",
        "is_holiday",
        "season_encoded",
    ]

    optional_cols = [
        "category",
        "cost",
        "stock_level"
    ]

    keep_cols = base_cols + [
        c for c in optional_cols
        if c in df.columns
    ]

    df = df[keep_cols].copy()

    # ─────────────────────────────────────────
    # Sort Chronologically
    # ─────────────────────────────────────────
    df = df.sort_values(
        ["product_id", "date"]
    ).reset_index(drop=True)

    # ─────────────────────────────────────────
    # Convert Dates Back to String
    # ─────────────────────────────────────────
    df["date"] = (
        df["date"]
        .dt.strftime("%Y-%m-%d")
    )

    return df


# ─────────────────────────────────────────────
# Prophet Product Time Series
# ─────────────────────────────────────────────
def get_product_timeseries(
    df: pd.DataFrame,
    product_id: str
) -> pd.DataFrame:
    """
    Returns Prophet-ready dataframe.

    Prophet expects:
        ds → datetime
        y  → target
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

    product_df["ds"] = pd.to_datetime(
        product_df["ds"],
        format="%Y-%m-%d",
        errors="coerce"
    )

    product_df = product_df.dropna(
        subset=["ds"]
    )

    required_cols = [
        "ds",
        "y",
        "is_weekend",
        "is_holiday",
        "season_encoded",
    ]

    available_cols = [
        c for c in required_cols
        if c in product_df.columns
    ]

    return product_df[
        available_cols
    ].sort_values(
        "ds"
    ).reset_index(drop=True)