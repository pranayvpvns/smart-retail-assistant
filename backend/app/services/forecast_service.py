import os
import joblib
import pandas as pd

from prophet import Prophet


MODEL_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "ml"
    )
)

# Cached models: {store_id: {product_id: bundle}}
_forecast_models_cache: dict[str, dict] = {}


# ─────────────────────────────────────────────
# Load Models
# ─────────────────────────────────────────────
def _load_models(store_id: str) -> dict:
    global _forecast_models_cache

    if store_id not in _forecast_models_cache:
        model_path = os.path.join(MODEL_DIR, f"forecast_{store_id}.pkl")
        
        if not os.path.exists(model_path):
            _forecast_models_cache[store_id] = {}
            return _forecast_models_cache[store_id]

        try:
            _forecast_models_cache[store_id] = joblib.load(model_path)
        except Exception:
            _forecast_models_cache[store_id] = {}

    return _forecast_models_cache[store_id]


# ─────────────────────────────────────────────
# Season Encoder
# ─────────────────────────────────────────────
def encode_season(month: int) -> int:
    if month in [12, 1, 2]: return 0   # Winter
    elif month in [3, 4, 5, 6]: return 1 # Summer
    elif month in [7, 8, 9]: return 2  # Monsoon
    return 3                           # Festive


# ─────────────────────────────────────────────
# Holiday Generator
# ─────────────────────────────────────────────
def is_holiday(date: pd.Timestamp) -> int:
    if date.weekday() == 6: return 1
    festive_dates = ["2026-01-01", "2026-10-24", "2026-12-25"]
    if str(date.date()) in festive_dates: return 1
    return 0


# ─────────────────────────────────────────────
# Forecast Generator
# ─────────────────────────────────────────────
def get_forecast(
    product_id: str,
    store_id: str,
    days: int = 14
) -> dict:
    """
    Generates context-aware demand forecast
    using Prophet + external regressors.
    """
    if days not in (7, 14, 30):
        raise ValueError("days must be 7, 14, or 30")

    models = _load_models(store_id)

    if product_id not in models:
        raise KeyError(
            f"No trained model found for product '{product_id}'. "
            "Forecasting requires at least 2 separate days of sales history. "
            "Please ensure you have enough data and click 'Retrain Models' to update."
        )

    model_bundle = models[product_id]
    model: Prophet = model_bundle["model"]

    # Build Future Dates
    future = model.make_future_dataframe(periods=days, freq="D")

    # Add Regressors
    future["is_weekend"] = pd.to_datetime(future["ds"]).dt.dayofweek.isin([5, 6]).astype(int)
    future["is_holiday"] = pd.to_datetime(future["ds"]).apply(is_holiday)
    future["season_encoded"] = pd.to_datetime(future["ds"]).dt.month.apply(encode_season)

    # Predict
    forecast_df = model.predict(future)
    forecast_df = forecast_df.tail(days).copy()

    # Prevent Forecast Explosion
    historical_mean = max(1, forecast_df["yhat"].mean())
    max_allowed = historical_mean * 3
    forecast_df["yhat"] = forecast_df["yhat"].clip(lower=0, upper=max_allowed)
    forecast_df["yhat_lower"] = forecast_df["yhat_lower"].clip(lower=0)
    forecast_df["yhat_upper"] = forecast_df["yhat_upper"].clip(lower=0)

    product_name = model_bundle.get("product_name", product_id)

    result = []
    for _, row in forecast_df.iterrows():
        result.append({
            "date": row["ds"].strftime("%Y-%m-%d"),
            "predicted_sales": round(float(row["yhat"]), 2),
            "lower_bound": round(float(row["yhat_lower"]), 2),
            "upper_bound": round(float(row["yhat_upper"]), 2),
            "is_weekend": int(row["is_weekend"]),
            "is_holiday": int(row["is_holiday"]),
            "season_encoded": int(row["season_encoded"]),
            "product_name": product_name,
        })

    return {
        "product_id": product_id,
        "product_name": product_name,
        "days": days,
        "forecast_type": "context-aware Prophet forecasting",
        "regressors_used": ["is_weekend", "is_holiday", "season_encoded"],
        "forecast": result,
    }


# ─────────────────────────────────────────────
# Available Products
# ─────────────────────────────────────────────
def get_available_products(store_id: str) -> list[str]:
    models = _load_models(store_id)
    return list(models.keys())


# ─────────────────────────────────────────────
# Reload Models
# ─────────────────────────────────────────────
def reload_models(store_id: str):
    global _forecast_models_cache
    if store_id in _forecast_models_cache:
        del _forecast_models_cache[store_id]
    _load_models(store_id)


# ─────────────────────────────────────────────
# Clear Models
# ─────────────────────────────────────────────
def clear_models(store_id: str):
    global _forecast_models_cache
    if store_id in _forecast_models_cache:
        del _forecast_models_cache[store_id]
    model_path = os.path.join(MODEL_DIR, f"forecast_{store_id}.pkl")
    if os.path.exists(model_path):
        os.remove(model_path)