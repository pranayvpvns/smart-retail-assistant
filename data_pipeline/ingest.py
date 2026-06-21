import pandas as pd
from io import BytesIO

# Required columns
REQUIRED_COLUMNS = [
    "date",
    "product_id",
    "product_name",
    "quantity_sold",
    "revenue",
    "store_id",
]

# Optional columns
OPTIONAL_COLUMNS = [
    "category",
    "cost",
    "stock_level"
]

# Numeric columns
NUMERIC_COLUMNS = [
    "quantity_sold",
    "revenue",
    "cost",
    "stock_level"
]


def ingest_csv(file_bytes: bytes) -> tuple[pd.DataFrame | None, list[str]]:
    """
    Reads CSV bytes, validates schema,
    and returns dataframe + validation errors.
    """

    errors = []

    # ─────────────────────────────────────────────
    # 1. Parse CSV
    # ─────────────────────────────────────────────
    try:
        df = pd.read_csv(BytesIO(file_bytes))

    except Exception as e:
        return None, [
            f"Could not parse CSV file: {str(e)}"
        ]

    if df.empty:
        return None, [
            "The uploaded CSV file is empty"
        ]

    # ─────────────────────────────────────────────
    # 2. Validate Required Columns
    # ─────────────────────────────────────────────
    missing_cols = [
        c for c in REQUIRED_COLUMNS
        if c not in df.columns
    ]

    if missing_cols:
        errors.append(
            f"Missing required columns: {', '.join(missing_cols)}"
        )

        return df, errors

    # ─────────────────────────────────────────────
    # 3. Check Empty Required Columns
    # ─────────────────────────────────────────────
    for col in REQUIRED_COLUMNS:

        if df[col].isnull().all():
            errors.append(
                f"Column '{col}' is entirely empty"
            )

    # ─────────────────────────────────────────────
    # 4. Validate Numeric Columns
    # ─────────────────────────────────────────────
    for col in NUMERIC_COLUMNS:

        if col in df.columns:

            converted = pd.to_numeric(
                df[col],
                errors="coerce"
            )

            bad_rows = (
                converted.isnull()
                & ~df[col].isnull()
            )

            bad_count = bad_rows.sum()

            if bad_count > 0:
                errors.append(
                    f"Column '{col}' has {bad_count} non-numeric value(s)"
                )

    # ─────────────────────────────────────────────
    # 5. Validate Dates (YYYY-MM-DD ONLY)
    # ─────────────────────────────────────────────
    cleaned_dates = (
        df["date"]
        .astype(str)
        .str.strip()
    )

    parsed_dates = pd.to_datetime(
        cleaned_dates,
        format="%Y-%m-%d",
        errors="coerce"
    )

    bad_dates = parsed_dates.isnull().sum()

    if bad_dates > 0:
        errors.append(
            f"{bad_dates} invalid date value(s). "
            "Expected format: YYYY-MM-DD"
        )

    df["date"] = parsed_dates

    return df, errors