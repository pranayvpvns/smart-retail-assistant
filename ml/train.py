import sys
import os

# ─────────────────────────────────────────────
# Configure Python Paths
# ─────────────────────────────────────────────

CURRENT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

PROJECT_ROOT = os.path.dirname(
    CURRENT_DIR
)

BACKEND_DIR = os.path.join(
    PROJECT_ROOT,
    "backend"
)

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

# ─────────────────────────────────────────────
# Imports
# ─────────────────────────────────────────────

import logging
import joblib
import pandas as pd
import numpy as np

from prophet import Prophet
from sklearn.ensemble import IsolationForest

from app.db.mongo import get_database
from app.config import get_settings

from ml.preprocessing import (
    load_sales_from_mongo,
    build_prophet_dataframe,
    build_anomaly_features,
    get_unique_products,
)

# ─────────────────────────────────────────────
# Model Paths
# ─────────────────────────────────────────────

MODEL_DIR = os.path.dirname(__file__)

FORECAST_MODEL_PATH = os.path.join(
    MODEL_DIR,
    "forecast_model.pkl"
)

ANOMALY_MODEL_PATH = os.path.join(
    MODEL_DIR,
    "anomaly_model.pkl"
)

# Suppress verbose logs
logging.getLogger("prophet").setLevel(
    logging.WARNING
)

logging.getLogger("cmdstanpy").setLevel(
    logging.WARNING
)


# ─────────────────────────────────────────────
# Train Prophet Forecast Models
# ─────────────────────────────────────────────
def train_forecast_models(
    df: pd.DataFrame,
    products: list[str]
) -> dict:
    """
    Trains Prophet forecasting models
    with external regressors.
    """

    models = {}

    for product_id in products:

        prophet_df = build_prophet_dataframe(
            df,
            product_id
        )

        # Need minimum rows
        if len(prophet_df) < 2:

            print(
                f"  ⚠️ Skipping {product_id} "
                f"— insufficient forecasting data"
            )

            continue

        # ─────────────────────────────────────
        # Prophet Model
        # ─────────────────────────────────────
        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
            seasonality_mode="multiplicative",
            interval_width=0.80,
        )

        # ─────────────────────────────────────
        # Add External Regressors
        # ─────────────────────────────────────
        model.add_regressor(
            "is_weekend"
        )

        model.add_regressor(
            "is_holiday"
        )

        model.add_regressor(
            "season_encoded"
        )

        # Train model
        model.fit(prophet_df)

        # Save model
        
        # Extract product name
        product_name = (
            df[df["product_id"] == product_id]
            ["product_name"]
            .iloc[0]
        )

        # Save model bundle
        models[product_id] = {
            "model": model,

            "product_name": product_name,

            "regressors": [
                "is_weekend",
                "is_holiday",
                "season_encoded",
            ]
        }



        print(
            f"  ✅ Forecast model trained "
            f"for {product_id}"
        )

    return models


# ─────────────────────────────────────────────
# Train Isolation Forest Models
# ─────────────────────────────────────────────
def train_anomaly_models(
    df: pd.DataFrame,
    products: list[str]
) -> dict:
    """
    Trains IsolationForest anomaly models.
    """

    models = {}

    for product_id in products:

        feature_df = build_anomaly_features(
            df,
            product_id
        )

        if len(feature_df) < 2:

            print(
                f"  ⚠️ Skipping {product_id} "
                f"anomaly — insufficient data"
            )

            continue

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
            if c in feature_df.columns
        ]

        X = feature_df[
            available
        ].values

        # Isolation Forest
        model = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=42,
        )

        model.fit(X)

        models[product_id] = {
            "model": model,
            "feature_cols": available,
        }

        print(
            f"  ✅ Anomaly model trained "
            f"for {product_id}"
        )

    return models


# ─────────────────────────────────────────────
# Main Training Pipeline
# ─────────────────────────────────────────────
def run_training(store_id: str):
    """
    End-to-end training pipeline.

    Loads data →
    trains Prophet + IsolationForest →
    saves store-specific .pkl files.
    """
    settings = get_settings()
    db = get_database()

    # Define store-specific paths
    forecast_path = os.path.join(MODEL_DIR, f"forecast_{store_id}.pkl")
    anomaly_path = os.path.join(MODEL_DIR, f"anomaly_{store_id}.pkl")

    print(f"\n🚀 Starting ML training for store: {store_id}")
    print("📦 Loading data from MongoDB...")

    df = load_sales_from_mongo(db, store_id)

    if df.empty:
        print("❌ No data found. Upload CSV or inject orders first.")
        return

    products = get_unique_products(df)
    print(f"🔍 Found {len(products)} products: {products}")
    print(f"📊 Total records: {len(df)}\n")

    # ─────────────────────────────────────
    # Forecast Training
    # ─────────────────────────────────────
    print("📈 Training Prophet models...")
    forecast_models = train_forecast_models(df, products)

    # ─────────────────────────────────────
    # Anomaly Training
    # ─────────────────────────────────────
    print("\n🔎 Training anomaly models...")
    anomaly_models = train_anomaly_models(df, products)

    # ─────────────────────────────────────
    # Save Models
    # ─────────────────────────────────────
    joblib.dump(forecast_models, forecast_path)
    joblib.dump(anomaly_models, anomaly_path)

    print(f"\n💾 Forecast models saved to: {forecast_path}")
    print(f"💾 Anomaly models saved to: {anomaly_path}")
    print(f"\n✅ Training complete: {len(forecast_models)} forecast, {len(anomaly_models)} anomaly models trained.\n")


# ─────────────────────────────────────────────
# CLI Entry
# ─────────────────────────────────────────────
if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--store-id",
        required=True,
        help=(
            "Store ID to train models for"
        )
    )

    args = parser.parse_args()

    run_training(
        args.store_id
    )