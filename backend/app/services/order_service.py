"""
order_service.py
────────────────
Handles the full order lifecycle:
  1. Validate stock availability for the vendor product
  2. Create order document in MongoDB
  3. Reduce stock atomically in vendor_products
  4. Append sale row to owner CSV (thread-safe)
  5. Upsert the sale into MongoDB sales_records for analytics
"""
from datetime import datetime, timezone

from pymongo.database import Database

from app.models.db_models import create_order_document
from app.services.csv_update_service import append_sale_row


# ─────────────────────────────────────────────────────────────
# Place Order
# ─────────────────────────────────────────────────────────────

def place_order(
    user_id: str,
    user_email: str,
    vendor_product_id: str,
    quantity: int,
    db: Database,
) -> dict:
    """
    Core order placement function.

    Returns:
        {"success": True,  "order": <order_dict>}          — on success
        {"success": False, "error": <reason_str>}           — on failure
    """
    vendor_col = db["vendor_products"]

    # ── 1. Fetch vendor product ──────────────────────────────
    vendor_product = vendor_col.find_one({"vendor_product_id": vendor_product_id})
    if not vendor_product:
        return {"success": False, "error": "Vendor product not found"}

    current_stock = vendor_product.get("stock", 0)
    if current_stock < quantity:
        return {
            "success": False,
            "error":   f"Insufficient stock. Available: {current_stock}, requested: {quantity}",
        }

    price_per_unit  = float(vendor_product.get("price", 0))
    cost_per_unit   = float(vendor_product.get("cost",  0))
    owner_id        = vendor_product["owner_id"]
    store_name      = vendor_product.get("store_name", "")
    product_name    = vendor_product.get("product_name", "")
    category        = vendor_product.get("category", "General")
    master_id       = vendor_product.get("master_product_id", "")

    # ── 2. Atomic stock reduction ────────────────────────────
    # Use $inc with a check to avoid race conditions
    update_result = vendor_col.update_one(
        {
            "vendor_product_id": vendor_product_id,
            "stock":             {"$gte": quantity},   # guard
        },
        {
            "$inc": {"stock": -quantity},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )
    if update_result.modified_count == 0:
        return {"success": False, "error": "Stock race condition — please try again"}

    new_stock = current_stock - quantity

    # ── 3. Create order document ─────────────────────────────
    order_doc = create_order_document(
        user_id=user_id,
        user_email=user_email,
        owner_id=owner_id,
        store_name=store_name,
        vendor_product_id=vendor_product_id,
        master_product_id=master_id,
        product_name=product_name,
        category=category,
        price_per_unit=price_per_unit,
        quantity=quantity,
    )
    db["orders"].insert_one(order_doc)
    order_doc.pop("_id", None)   # strip MongoDB internal _id before returning

    # ── 4. Append to owner CSV (thread-safe) ─────────────────
    revenue = price_per_unit * quantity
    cost    = cost_per_unit  * quantity

    csv_result = append_sale_row(
        store_id=owner_id,
        product_id=vendor_product_id,
        product_name=product_name,
        category=category,
        quantity_sold=quantity,
        revenue=revenue,
        cost=cost,
        new_stock_level=new_stock,
    )
    if not csv_result["success"]:
        # Non-fatal — log but don't roll back the order
        print(f"⚠️  CSV append failed for order {order_doc['order_id']}: {csv_result['error']}")

    # ── 5. Upsert sale into MongoDB sales_records ────────────
    _upsert_sales_record(
        db=db,
        order_doc=order_doc,
        cost=cost,
        new_stock=new_stock,
    )

    return {
        "success": True,
        "order":   _serialize(order_doc),
        "csv_updated": csv_result["success"],
    }


# ─────────────────────────────────────────────────────────────
# Order History Queries
# ─────────────────────────────────────────────────────────────

def get_user_orders(user_id: str, db: Database, page: int = 1, limit: int = 20) -> dict:
    """Returns paginated order history for a buyer."""
    skip  = (page - 1) * limit
    query = {"user_id": user_id}
    total = db["orders"].count_documents(query)
    docs  = list(
        db["orders"]
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return {"total": total, "page": page, "limit": limit, "orders": [_serialize(d) for d in docs]}


def get_owner_orders(owner_id: str, db: Database, page: int = 1, limit: int = 50) -> dict:
    """Returns paginated order history for an owner's store."""
    skip  = (page - 1) * limit
    query = {"owner_id": owner_id}
    total = db["orders"].count_documents(query)
    docs  = list(
        db["orders"]
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return {"total": total, "page": page, "limit": limit, "orders": [_serialize(d) for d in docs]}


# ─────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────

def _upsert_sales_record(db: Database, order_doc: dict, cost: float, new_stock: int):
    """Inserts/updates a sales_records entry so analytics reflect the new sale."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record = {
        "date":          today,
        "product_id":    order_doc["vendor_product_id"],
        "product_name":  order_doc["product_name"],
        "quantity_sold": order_doc["quantity"],
        "revenue":       order_doc["total_amount"],
        "store_id":      order_doc["owner_id"],
        "category":      order_doc["category"],
        "cost":          round(cost, 2),
        "stock_level":   new_stock,
    }
    db["sales_records"].update_one(
        filter={
            "date":       today,
            "product_id": record["product_id"],
            "store_id":   record["store_id"],
        },
        update={"$set": record},
        upsert=True,
    )


def _serialize(doc: dict) -> dict:
    """Convert datetime objects to ISO strings for JSON serialization."""
    out = {}
    for k, v in doc.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
