"""
product_service.py
──────────────────
Handles:
  • CSV → master product + vendor product mapping on upload
  • Marketplace browsing queries (all products, search, filter)
  • Per-product multi-vendor listing
"""
import io
import uuid
from datetime import datetime, timezone

import pandas as pd
from pymongo.database import Database

from app.models.db_models import (
    create_master_product_document,
    create_vendor_product_document,
)


# ─────────────────────────────────────────────────────────────
# CSV → Catalog Mapping
# ─────────────────────────────────────────────────────────────

def sync_catalog_from_dataframe(
    df: pd.DataFrame,
    store_id: str,
    store_name: str,
    db: Database,
) -> dict:
    """
    Given a cleaned sales DataFrame (already stamped with store_id),
    upserts master products and vendor product listings.

    Called automatically after CSV upload so the marketplace
    catalog stays in sync with owner datasets.
    """
    master_col  = db["master_products"]
    vendor_col  = db["vendor_products"]

    created_master  = 0
    upserted_vendor = 0

    # Determine product name column (flexible column names)
    name_col     = _find_col(df, ["product_name", "product", "name", "item"])
    cat_col      = _find_col(df, ["category", "cat"])
    price_col    = _find_col(df, ["price", "unit_price", "selling_price", "revenue"])
    cost_col     = _find_col(df, ["cost", "unit_cost", "cost_price"])
    stock_col    = _find_col(df, ["stock_level", "stock", "inventory", "units_in_stock"])
    product_id_col = _find_col(df, ["product_id", "sku", "item_id"])

    if name_col is None:
        return {"success": False, "error": "No product name column found in CSV"}

    # ── Detect quantity column ──────────────────────────────────
    qty_col      = _find_col(df, ["quantity_sold", "quantity", "units_sold", "qty"])

    # ── Derive unit price ───────────────────────────────────────
    # If there is a direct price column use it; otherwise compute
    # unit_price = revenue / quantity_sold so we don't mistake
    # total-transaction revenue for a per-unit price.
    direct_price_col = _find_col(df, ["price", "unit_price", "selling_price"])
    if direct_price_col:
        df["_unit_price"] = pd.to_numeric(df[direct_price_col], errors="coerce")
    elif price_col and qty_col:
        rev  = pd.to_numeric(df[price_col], errors="coerce").fillna(0)
        qty  = pd.to_numeric(df[qty_col],   errors="coerce").replace(0, 1)
        df["_unit_price"] = (rev / qty).round(2)
    elif price_col:
        df["_unit_price"] = pd.to_numeric(df[price_col], errors="coerce")
    else:
        df["_unit_price"] = 0.0

    # ── Derive unit cost ────────────────────────────────────────
    if cost_col and qty_col:
        c   = pd.to_numeric(df[cost_col], errors="coerce").fillna(0)
        qty = pd.to_numeric(df[qty_col],  errors="coerce").replace(0, 1)
        # Heuristic: if max cost < max unit_price it's already a unit cost
        if df[cost_col].max() < df["_unit_price"].max() * 1.2:
            df["_unit_cost"] = pd.to_numeric(df[cost_col], errors="coerce")
        else:
            df["_unit_cost"] = (c / qty).round(2)
    elif cost_col:
        df["_unit_cost"] = pd.to_numeric(df[cost_col], errors="coerce")
    else:
        df["_unit_cost"] = 0.0

    # ── Deduplicated snapshot per product ───────────────────────
    group_cols = [c for c in [name_col, cat_col] if c is not None]
    snapshot = df.groupby(group_cols).agg(
        _avg_price=("_unit_price", "mean"),
        _avg_cost=("_unit_cost",  "mean"),
        _stock=(stock_col, "last") if stock_col else ("_unit_price", "count"),
    ).reset_index()

    for _, row in snapshot.iterrows():
        product_name = str(row[name_col]).strip()
        category     = str(row[cat_col]).strip() if cat_col else "General"

        # ── 1. Upsert master product ──────────────────────────
        existing_master = master_col.find_one(
            {"product_name": {"$regex": f"^{_re_escape(product_name)}$", "$options": "i"}}
        )
        if existing_master:
            master_product_id = existing_master["product_id"]
        else:
            doc = create_master_product_document(
                product_name=product_name,
                category=category,
            )
            master_col.insert_one(doc)
            master_product_id = doc["product_id"]
            created_master += 1

        # ── 2. Upsert vendor product ──────────────────────────
        price = round(float(row.get("_avg_price", 0) or 0), 2)
        cost  = round(float(row.get("_avg_cost",  0) or 0), 2)
        stock = int(row.get("_stock", 0) or 0)


        vendor_doc = create_vendor_product_document(
            owner_id=store_id,
            store_name=store_name,
            master_product_id=master_product_id,
            product_name=product_name,
            category=category,
            price=price,
            cost=cost,
            stock=stock,
        )

        existing_vendor = vendor_col.find_one({
            "owner_id":          store_id,
            "master_product_id": master_product_id,
        })
        if existing_vendor:
            vendor_col.update_one(
                {"_id": existing_vendor["_id"]},
                {"$set": {
                    "price":      vendor_doc["price"],
                    "cost":       vendor_doc["cost"],
                    "stock":      vendor_doc["stock"],
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
        else:
            vendor_col.insert_one(vendor_doc)
            upserted_vendor += 1

    return {
        "success":         True,
        "created_master":  created_master,
        "upserted_vendor": upserted_vendor,
    }


# ─────────────────────────────────────────────────────────────
# Owner Inventory Queries
# ─────────────────────────────────────────────────────────────

def get_owner_inventory(store_id: str, db: Database) -> list:
    """Returns all vendor products belonging to a specific owner."""
    vendor_col = db["vendor_products"]
    products   = list(vendor_col.find({"owner_id": store_id}, {"_id": 0}))
    return products


def update_owner_product(
    vendor_product_id: str,
    store_id: str,
    db: Database,
    updates: dict,
) -> dict:
    """
    Allows owner to update price / stock / delivery_time for their
    own vendor product. Ignores unknown fields.
    """
    allowed = {"price", "stock", "delivery_time", "rating"}
    safe_updates = {k: v for k, v in updates.items() if k in allowed}
    if not safe_updates:
        return {"success": False, "error": "No valid fields to update"}

    safe_updates["updated_at"] = datetime.now(timezone.utc)

    result = db["vendor_products"].update_one(
        {"vendor_product_id": vendor_product_id, "owner_id": store_id},
        {"$set": safe_updates},
    )
    if result.matched_count == 0:
        return {"success": False, "error": "Product not found or access denied"}
    return {"success": True, "updated": safe_updates}


# ─────────────────────────────────────────────────────────────
# Marketplace / User Browsing
# ─────────────────────────────────────────────────────────────

def get_marketplace_products(
    db: Database,
    search: str = "",
    category: str = "",
    page: int = 1,
    limit: int = 20,
) -> dict:
    """
    Returns paginated master products enriched with vendor listings.
    Supports search by name and category filter.
    """
    master_col = db["master_products"]
    vendor_col = db["vendor_products"]

    query: dict = {}
    if search:
        query["product_name"] = {"$regex": search, "$options": "i"}
    if category:
        query["category"] = {"$regex": f"^{_re_escape(category)}$", "$options": "i"}

    total = master_col.count_documents(query)
    skip  = (page - 1) * limit

    masters = list(
        master_col.find(query, {"_id": 0})
        .skip(skip)
        .limit(limit)
    )

    # Enrich each master product with vendor options
    result = []
    for mp in masters:
        vendors_raw = list(vendor_col.find(
            {"master_product_id": mp["product_id"], "stock": {"$gt": 0}},
            {"_id": 0, "owner_id": 0},   # hide internal owner_id
        ))
        # Sort cheapest first
        vendors_raw.sort(key=lambda v: v.get("price", 0))
        result.append({
            "product_id":   mp["product_id"],
            "product_name": mp["product_name"],
            "category":     mp["category"],
            "description":  mp.get("description", ""),
            "image_url":    mp.get("image_url", ""),
            "vendor_count": len(vendors_raw),
            "min_price":    vendors_raw[0]["price"] if vendors_raw else None,
            "vendors":      vendors_raw,
        })

    return {
        "total":    total,
        "page":     page,
        "limit":    limit,
        "products": result,
    }


def get_product_detail(product_id: str, db: Database) -> dict | None:
    """
    Returns master product + all vendor listings (in-stock and out-of-stock).
    """
    master_col = db["master_products"]
    vendor_col = db["vendor_products"]

    mp = master_col.find_one({"product_id": product_id}, {"_id": 0})
    if not mp:
        return None

    vendors = list(vendor_col.find(
        {"master_product_id": product_id},
        {"_id": 0, "owner_id": 0},
    ))
    vendors.sort(key=lambda v: v.get("price", 0))

    return {
        "product_id":   mp["product_id"],
        "product_name": mp["product_name"],
        "category":     mp["category"],
        "description":  mp.get("description", ""),
        "image_url":    mp.get("image_url", ""),
        "vendors":      vendors,
    }


def get_categories(db: Database) -> list:
    """Returns distinct product categories from the master catalog."""
    return db["master_products"].distinct("category")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _find_col(df: pd.DataFrame, candidates: list) -> str | None:
    """Returns first matching column name (case-insensitive)."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def _re_escape(s: str) -> str:
    """Minimal regex escaping for MongoDB $regex."""
    special = r"\.^$*+?{}[]|()"
    return "".join(f"\\{c}" if c in special else c for c in s)
