"""
routes/orders.py  (rewrite)
───────────────────────────
User:
  POST  /api/v1/orders              — place order
  GET   /api/v1/orders              — buyer's order history

Owner:
  GET   /api/v1/orders/pending      — pending orders (notification feed)
  GET   /api/v1/orders/all          — all store orders (paginated)
  POST  /api/v1/orders/<id>/inject  — inject into selected dataset
  POST  /api/v1/orders/<id>/reject  — reject order (restores stock)
"""
from flask import Blueprint, request, jsonify, g

from app.utils.auth_helpers import token_required, role_required
from app.services.order_flow_service import (
    place_order,
    get_pending_orders,
    get_all_store_orders,
    get_user_orders,
    inject_order,
    reject_order,
)
from app.db.mongo import get_database

orders_bp = Blueprint("orders", __name__, url_prefix="/api/v1/orders")


# ─── User: Place Order ─────────────────────────────────────────
@orders_bp.route("", methods=["POST"])
@token_required
@role_required("user")
def create_order():
    body = request.get_json(force=True) or {}
    product_id = body.get("product_id", "").strip()
    quantity   = int(body.get("quantity", 1))
    if not product_id or quantity < 1:
        return jsonify({"error": "product_id and quantity (≥1) are required"}), 422

    db   = get_database()
    user = g.current_user
    user_id = user.get("user_id") or user.get("email", "")

    result = place_order(
        user_id=user_id,
        user_email=user["email"],
        product_id=product_id,
        quantity=quantity,
        db=db,
    )
    return jsonify(result), 201 if result["success"] else 400


# ─── User: Order History ───────────────────────────────────────
@orders_bp.route("", methods=["GET"])
@token_required
@role_required("user")
def user_order_history():
    page  = max(1, int(request.args.get("page",  1)))
    limit = min(50, max(1, int(request.args.get("limit", 20))))
    db    = get_database()
    user  = g.current_user
    user_id = user.get("user_id") or user.get("email", "")
    result = get_user_orders(user_id=user_id, db=db, page=page, limit=limit)
    return jsonify(result), 200


# ─── Owner: Pending Orders (notifications) ────────────────────
@orders_bp.route("/pending", methods=["GET"])
@token_required
@role_required("owner")
def pending_orders():
    db     = get_database()
    orders = get_pending_orders(owner_id=g.current_user["store_id"], db=db)
    return jsonify({"pending": orders, "count": len(orders)}), 200


# ─── Owner: All Store Orders ───────────────────────────────────
@orders_bp.route("/all", methods=["GET"])
@token_required
@role_required("owner")
def all_store_orders():
    page  = max(1, int(request.args.get("page",  1)))
    limit = min(100, max(1, int(request.args.get("limit", 50))))
    db    = get_database()
    result = get_all_store_orders(
        owner_id=g.current_user["store_id"], db=db, page=page, limit=limit
    )
    return jsonify(result), 200


# ─── Owner: Inject Order into Dataset ─────────────────────────
@orders_bp.route("/<order_id>/inject", methods=["POST"])
@token_required
@role_required("owner")
def inject_order_route(order_id: str):
    body       = request.get_json(force=True) or {}
    dataset_id = body.get("dataset_id", "").strip()
    if not dataset_id:
        return jsonify({"error": "dataset_id is required"}), 422

    db     = get_database()
    result = inject_order(
        order_id=order_id,
        dataset_id=dataset_id,
        owner_id=g.current_user["store_id"],
        db=db,
    )
    return jsonify(result), 200 if result["success"] else 400


@orders_bp.route("/<order_id>/inject-external", methods=["POST"])
@token_required
@role_required("owner")
def inject_external_route(order_id: str):
    """
    POST /api/v1/orders/<id>/inject-external
    Used when the user manually updates their local file (e.g. via Browser File System API).
    Marks order as injected and updates MongoDB records, but does NOT touch CSV.
    """
    from datetime import datetime, timezone
    db = get_database()
    store_id = g.current_user["store_id"]

    order = db["ordered_sales"].find_one({"order_id": order_id, "owner_id": store_id})
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["order_status"] != "pending":
        return jsonify({"error": f"Order is {order['order_status']}"}), 400

    # 1. Update order status
    db["ordered_sales"].update_one(
        {"_id": order["_id"]},
        {"$set": {
            "order_status": "injected",
            "injected_dataset_id": "external",
            "injected_at": datetime.now(timezone.utc),
        }}
    )

    product_id = order.get("vendor_product_id") or order.get("product_id")
    quantity = order.get("quantity") or 1
    revenue = order.get("total_amount") or order.get("total_price") or 0

    # 2. Add to sales_records in DB for analytics consistency (daily aggregation)
    db["sales_records"].update_one(
        filter={
            "date":        order["ordered_at"].strftime("%Y-%m-%d"),
            "product_id":  product_id,
            "store_id":    store_id,
        },
        update={
            "$inc": {
                "quantity_sold": quantity,
                "revenue":       revenue,
            },
            "$set": {
                "created_at":  datetime.now(timezone.utc),
                "updated_at":  datetime.now(timezone.utc),
            }
        },
        upsert=True
    )

    return jsonify({"success": True, "message": "Order marked as externally injected"}), 200


# ─── Owner: Reject Order ──────────────────────────────────────
@orders_bp.route("/<order_id>/reject", methods=["POST"])
@token_required
@role_required("owner")
def reject_order_route(order_id: str):
    db     = get_database()
    result = reject_order(
        order_id=order_id,
        owner_id=g.current_user["store_id"],
        db=db,
    )
    return jsonify(result), 200 if result["success"] else 400
