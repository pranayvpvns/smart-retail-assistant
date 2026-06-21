from flask import Blueprint, request, jsonify, g
from app.utils.auth_helpers import token_required
from app.db.mongo import get_database
from app.services.forecast_service import (
    get_forecast,
    get_available_products,
    reload_models,
)

forecast_bp = Blueprint("forecast", __name__, url_prefix="/api/v1/forecast")


@forecast_bp.route("/<product_id>", methods=["GET"])
@token_required
def forecast(product_id: str):
    """
    GET /api/v1/forecast/<product_id>?days=14
    Auth: Bearer token required
    days: 7 | 14 | 30 (default 14)
    """
    store_id = g.current_user["store_id"]
    try:
        days = int(request.args.get("days", 14))
    except ValueError:
        return jsonify({"error": "days must be an integer: 7, 14, or 30"}), 400

    try:
        result = get_forecast(product_id=product_id, store_id=store_id, days=days)
        return jsonify(result), 200

    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503

    except KeyError as e:
        return jsonify({"error": str(e)}), 404

    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    except Exception as e:
        return jsonify({"error": f"Forecasting failed: {str(e)}"}), 500


@forecast_bp.route("/products", methods=["GET"])
@token_required
def available_products():
    """
    GET /api/v1/forecast/products
    Returns list of products with ID and Name.
    """
    db = get_database()
    store_id = g.current_user["store_id"]
    
    try:
        # Get all products from forecast models if any exist for this store
        trained_products = get_available_products(store_id=store_id)
        
        # 1. Map IDs to Names from Catalog
        catalog_docs = list(db["products"].find({"owner_id": store_id}, {"product_id": 1, "product_name": 1, "_id": 0}))
        product_map = {p["product_id"]: p.get("product_name", p["product_id"]) for p in catalog_docs}
        
        # 2. Add names from Sales Records for any products not in catalog
        sales_ids = db["sales_records"].distinct("product_id", {"store_id": store_id})
        missing_ids = [pid for pid in sales_ids if pid not in product_map]
        
        if missing_ids:
            sales_docs = list(db["sales_records"].find(
                {"product_id": {"$in": missing_ids}, "store_id": store_id},
                {"product_id": 1, "product_name": 1, "_id": 0}
            ))
            for p in sales_docs:
                if p["product_id"] not in product_map:
                    product_map[p["product_id"]] = p.get("product_name", p["product_id"])
        
        # Build final list of objects
        final_products = {}
        for pid, name in product_map.items():
            if name not in final_products:
                final_products[name] = pid
            else:
                old_pid = final_products[name]
                count_new = db["sales_records"].count_documents({"product_id": pid, "store_id": store_id})
                count_old = db["sales_records"].count_documents({"product_id": old_pid, "store_id": store_id})
                if count_new > count_old:
                    final_products[name] = pid
        
        products_list = [{"id": pid, "name": name} for name, pid in final_products.items()]
        products_list.sort(key=lambda x: x["name"].lower())
        
        return jsonify({"products": products_list}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch products: {str(e)}"}), 500


@forecast_bp.route("/retrain", methods=["POST"])
@token_required
def retrain():
    """
    POST /api/v1/forecast/retrain
    Triggers full model retraining from current data in MongoDB.
    """
    store_id = g.current_user["store_id"]

    try:
        import sys, os
        from ml.train import run_training
        run_training(store_id)

        # Reload in-memory caches for this specific store
        reload_models(store_id=store_id)
        from app.services.anomaly_service import reload_models as reload_anomaly
        reload_anomaly(store_id=store_id)

        return jsonify({"message": "Models retrained and reloaded successfully"}), 200
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Retraining failed: {str(e)}"}), 500
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Retraining failed: {str(e)}"}), 500