import os
import joblib
import numpy as np
import pandas as pd

from datetime import datetime, timezone
from pymongo.database import Database

from ml.preprocessing import (
    load_sales_from_mongo,
    build_anomaly_features
)

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
_anomaly_models_cache: dict[str, dict] = {}


# ─────────────────────────────────────────────
# Load Models
# ─────────────────────────────────────────────
def _load_models(store_id: str) -> dict:
    global _anomaly_models_cache

    if store_id not in _anomaly_models_cache:
        model_path = os.path.join(MODEL_DIR, f"anomaly_{store_id}.pkl")
        
        if not os.path.exists(model_path):
            _anomaly_models_cache[store_id] = {}
            return _anomaly_models_cache[store_id]

        try:
            _anomaly_models_cache[store_id] = joblib.load(model_path)
        except Exception:
            _anomaly_models_cache[store_id] = {}

    return _anomaly_models_cache[store_id]


# ─────────────────────────────────────────────
# Main Detection Logic
# ─────────────────────────────────────────────
def run_anomaly_detection(
    store_id: str,
    db: Database
) -> dict:

    models = _load_models(store_id)

    df = load_sales_from_mongo(
        db=db,
        store_id=store_id
    )

    if df.empty:
        return {
            "success": False,
            "error": "No sales data found for this store"
        }

    alerts_collection = db["alerts"]
    # Remove previous alerts for this store
    alerts_collection.delete_many({
        "store_id": store_id
    })

    new_alerts = 0
    products_scanned = 0
    critical_alerts = 0
    warning_alerts = 0

    current_products = sorted(df["product_id"].unique().tolist())

    for product_id in current_products:
        feature_df = build_anomaly_features(df, product_id)
        if feature_df.empty: continue

        # Use pre-trained model if available, otherwise train inline
        if product_id in models:
            model_bundle = models[product_id]
        else:
            # Inline training requires at least 5 points
            from sklearn.ensemble import IsolationForest
            feature_cols = ["quantity_sold", "revenue", "rolling_mean_7", "rolling_std_7", "lag_1", "lag_7", "day_of_week"]
            available = [c for c in feature_cols if c in feature_df.columns]
            
            if len(feature_df) < 5 or not available:
                continue

            X_inline = feature_df[available].values
            model_inline = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
            model_inline.fit(X_inline)
            model_bundle = {"model": model_inline, "feature_cols": available}

        model = model_bundle["model"]
        feature_cols = model_bundle["feature_cols"]
        available_features = [c for c in feature_cols if c in feature_df.columns]
        if not available_features: continue

        X = feature_df[available_features].values
        predictions = model.predict(X)
        scores = model.decision_function(X)
        avg_quantity = feature_df["quantity_sold"].mean()

        for i, (idx, row) in enumerate(feature_df.iterrows()):
            quantity = float(row["quantity_sold"])
            stock_level = row.get("stock_level", None)
            score = float(scores[i])
            deviation_percent = (abs(quantity - avg_quantity) / max(avg_quantity, 1)) * 100
            
            ml_anomaly = predictions[i] == -1
            business_anomaly = (deviation_percent >= 120 or (stock_level is not None and stock_level <= 5))

            if ml_anomaly or business_anomaly:
                product_name = row.get("product_name", product_id)
                
                # Determine Severity
                if deviation_percent >= 120 or score < -0.05 or (stock_level is not None and stock_level <= 5 and deviation_percent >= 50):
                    severity = "critical"
                    critical_alerts += 1
                else:
                    severity = "warning"
                    warning_alerts += 1

                # Build message
                diff_type = "increased" if quantity > avg_quantity else "dropped"
                message = f"{severity.upper()} ALERT: '{product_name}' sales {diff_type} {round(deviation_percent, 1)}% relative to normal."
                if stock_level is not None and stock_level <= 5:
                    message += f" Stock is critically low ({stock_level})."

                alert_doc = {
                    "store_id": store_id,
                    "product_id": product_id,
                    "product_name": product_name,
                    "date": str(row["date"]),
                    "quantity_sold": quantity,
                    "average_quantity": round(avg_quantity, 2),
                    "deviation_percent": round(deviation_percent, 2),
                    "severity": severity,
                    "anomaly_score": round(score, 4),
                    "stock_level": stock_level,
                    "message": message,
                    "detected_at": datetime.now(timezone.utc),
                    "acknowledged": False,
                }

                alerts_collection.update_one(
                    filter={"store_id": store_id, "product_id": product_id, "date": str(row["date"])},
                    update={"$set": alert_doc},
                    upsert=True,
                )
                new_alerts += 1

        products_scanned += 1

    return {
        "success": True,
        "products_scanned": products_scanned,
        "alerts_generated": new_alerts,
        "critical_alerts": critical_alerts,
        "warning_alerts": warning_alerts,
    }


def get_alerts(store_id: str, db: Database, severity: str | None = None) -> list[dict]:
    query = {"store_id": store_id}
    if severity in ("warning", "critical"): query["severity"] = severity
    alerts = list(db["alerts"].find(query, {"_id": 0}).sort("detected_at", -1).limit(100))
    for alert in alerts:
        if isinstance(alert.get("detected_at"), datetime):
            alert["detected_at"] = alert["detected_at"].isoformat()
    return alerts


def reload_models(store_id: str):
    global _anomaly_models_cache
    if store_id in _anomaly_models_cache:
        del _anomaly_models_cache[store_id]
    _load_models(store_id)


def clear_models(store_id: str):
    global _anomaly_models_cache
    if store_id in _anomaly_models_cache:
        del _anomaly_models_cache[store_id]
    model_path = os.path.join(MODEL_DIR, f"anomaly_{store_id}.pkl")
    if os.path.exists(model_path):
        os.remove(model_path)