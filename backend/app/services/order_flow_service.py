"""
order_flow_service.py
──────────────────────
Handles the new order lifecycle:

  1. place_order       — creates ordered_sale, reduces product stock
  2. get_pending_orders — owner notification feed
  3. get_all_orders     — complete order history for owner
  4. get_user_orders    — buyer's own order history
  5. inject_order       — owner approves + selects dataset → appends sale
  6. reject_order       — owner rejects an order
"""
from datetime import datetime, timezone

from pymongo.database import Database

from app.models.db_models import create_ordered_sale_document
from app.services.dataset_service import append_sale_to_dataset
from app.services.product_catalog_service import sync_products_csv


# ─────────────────────────────────────────────────────────────
# Place Order  (buyer action)
# ─────────────────────────────────────────────────────────────

def place_order(
    user_id: str,
    user_email: str,
    product_id: str,
    quantity: int,
    db: Database,
) -> dict:
    """
    Validates stock, creates an ordered_sale document (status=pending),
    and atomically reduces product stock.

    Does NOT touch sales_records or any analytics dataset.
    """
    # ── Fetch product ────────────────────────────────────────
    product = db["products"].find_one({"product_id": product_id})
    if not product:
        return {"success": False, "error": "Product not found"}

    current_stock = product.get("stock", 0)
    if current_stock < quantity:
        return {
            "success": False,
            "error":   f"Insufficient stock. Available: {current_stock}, requested: {quantity}",
        }

    owner_id    = product["owner_id"]
    store_name  = product.get("store_name", "")
    price_unit  = float(product.get("price", 0))
    category    = product.get("category", "General")
    product_name = product["product_name"]

    # ── Atomic stock reduction ───────────────────────────────
    result = db["products"].update_one(
        {"product_id": product_id, "stock": {"$gte": quantity}},
        {
            "$inc": {"stock": -quantity},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )
    if result.modified_count == 0:
        return {"success": False, "error": "Stock changed concurrently. Please retry."}

    # ── Create ordered_sale ──────────────────────────────────
    order_doc = create_ordered_sale_document(
        user_id=user_id,
        user_email=user_email,
        owner_id=owner_id,
        store_name=store_name,
        product_id=product_id,
        product_name=product_name,
        category=category,
        price_per_unit=price_unit,
        quantity=quantity,
    )
    db["ordered_sales"].insert_one(order_doc)
    order_doc.pop("_id", None)

    # ── Sync products.csv to reflect reduced stock ────────────
    sync_products_csv(owner_id, db)

    return {"success": True, "order": _serialize(order_doc)}


# ─────────────────────────────────────────────────────────────
# Owner — Pending Orders  (notification feed)
# ─────────────────────────────────────────────────────────────

def get_pending_orders(owner_id: str, db: Database) -> list:
    """Returns pending orders for the owner's store, newest first."""
    docs = list(
        db["ordered_sales"]
        .find({"owner_id": owner_id, "order_status": "pending"}, {"_id": 0})
        .sort("ordered_at", -1)
    )
    return [_serialize(d) for d in docs]


def get_all_store_orders(
    owner_id: str, db: Database, page: int = 1, limit: int = 50
) -> dict:
    """Paginated complete order list for an owner."""
    skip  = (page - 1) * limit
    query = {"owner_id": owner_id}
    total = db["ordered_sales"].count_documents(query)
    docs  = list(
        db["ordered_sales"]
        .find(query, {"_id": 0})
        .sort("ordered_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return {"total": total, "page": page, "limit": limit, "orders": [_serialize(d) for d in docs]}


# ─────────────────────────────────────────────────────────────
# Buyer — Order History
# ─────────────────────────────────────────────────────────────

def get_user_orders(
    user_id: str, db: Database, page: int = 1, limit: int = 20
) -> dict:
    skip  = (page - 1) * limit
    query = {"user_id": user_id}
    total = db["ordered_sales"].count_documents(query)
    docs  = list(
        db["ordered_sales"]
        .find(query, {"_id": 0})
        .sort("ordered_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return {"total": total, "page": page, "limit": limit, "orders": [_serialize(d) for d in docs]}


# ─────────────────────────────────────────────────────────────
# Owner — Inject Order into Dataset
# ─────────────────────────────────────────────────────────────

def inject_order(
    order_id: str,
    dataset_id: str,
    owner_id: str,
    db: Database,
) -> dict:
    """
    Owner selects a dataset and approves injection.

    Steps:
      1. Validate order belongs to owner and is still pending
      2. Call dataset_service.append_sale_to_dataset (CSV + MongoDB)
      3. Mark order as injected
      4. Trigger analytics model refresh (optional, non-fatal)
    """
    order = db["ordered_sales"].find_one({"order_id": order_id, "owner_id": owner_id})
    if not order:
        return {"success": False, "error": "Order not found or access denied"}
    if order["order_status"] != "pending":
        return {"success": False, "error": f"Order is already {order['order_status']}"}

    # ── Append to dataset ────────────────────────────────────
    inject_result = append_sale_to_dataset(
        dataset_id=dataset_id,
        owner_id=owner_id,
        order=order,
        db=db,
    )
    if not inject_result["success"]:
        return inject_result

    # ── Mark order as injected ────────────────────────────────
    db["ordered_sales"].update_one(
        {"_id": order["_id"]},
        {"$set": {
            "order_status":       "injected",
            "injected_dataset_id": dataset_id,
            "injected_at":        datetime.now(timezone.utc),
        }},
    )

    # ── Trigger model refresh (non-fatal) ────────────────────
    _trigger_retrain(owner_id)

    return {
        "success":    True,
        "order_id":   order_id,
        "dataset_id": dataset_id,
        "csv_path":   inject_result.get("csv_path"),
    }


# ─────────────────────────────────────────────────────────────
# Owner — Reject Order
# ─────────────────────────────────────────────────────────────

def reject_order(order_id: str, owner_id: str, db: Database) -> dict:
    """
    Owner rejects a pending order.
    Restores product stock so the item is available again.
    """
    order = db["ordered_sales"].find_one({"order_id": order_id, "owner_id": owner_id})
    if not order:
        return {"success": False, "error": "Order not found or access denied"}
    if order["order_status"] != "pending":
        return {"success": False, "error": f"Order is already {order['order_status']}"}

    # Restore stock
    db["products"].update_one(
        {"product_id": order["product_id"]},
        {
            "$inc": {"stock": order["quantity"]},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )
    sync_products_csv(owner_id, db)

    db["ordered_sales"].update_one(
        {"_id": order["_id"]},
        {"$set": {"order_status": "rejected"}},
    )
    return {"success": True, "order_id": order_id, "stock_restored": order["quantity"]}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in doc.items()}


def _trigger_retrain(store_id: str) -> None:
    """Reload in-memory model caches after an injection. Non-fatal."""
    try:
        from app.services.forecast_service import reload_models
        from app.services.anomaly_service  import reload_models as reload_anomaly
        reload_models(store_id=store_id)
        reload_anomaly(store_id=store_id)
    except Exception as exc:
        print(f"⚠️  Post-injection retrain skipped: {exc}")
