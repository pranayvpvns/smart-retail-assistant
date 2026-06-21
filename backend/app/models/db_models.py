from datetime import datetime, timezone
import uuid


# ─────────────────────────────────────────────────────────────
# User Documents
# ─────────────────────────────────────────────────────────────

def create_user_document(
    email: str,
    hashed_password: str,
    store_name: str,
    store_id: str,
    role: str = "owner",
    name: str = "",
) -> dict:
    return {
        "email":      email,
        "password":   hashed_password,
        "store_name": store_name,
        "store_id":   store_id,
        "role":       role,
        "name":       name,
        "created_at": datetime.now(timezone.utc),
        "is_active":  True,
    }


# ─────────────────────────────────────────────────────────────
# Product Documents  (owner-managed standalone product catalog)
# ─────────────────────────────────────────────────────────────

def create_product_document(
    owner_id: str,
    store_name: str,
    product_name: str,
    category: str,
    price: float,
    stock: int,
    description: str = "",
    image_url: str = "",
    cost: float = 0.0,
) -> dict:
    """
    Owner's product listing. Lives in the 'products' collection
    and is mirrored to products.csv. Completely separate from
    the analytics sales_records pipeline.
    """
    return {
        "product_id":   f"PRD-{uuid.uuid4().hex[:12].upper()}",
        "owner_id":     owner_id,
        "store_name":   store_name,
        "product_name": product_name.strip(),
        "category":     (category or "General").strip(),
        "price":        round(float(price), 2),
        "cost":         round(float(cost), 2),
        "stock":        max(0, int(stock)),
        "description":  description.strip(),
        "image_url":    image_url.strip(),
        "created_at":   datetime.now(timezone.utc),
        "updated_at":   datetime.now(timezone.utc),
    }


# ─────────────────────────────────────────────────────────────
# Ordered Sale Documents  (customer orders — not analytics data)
# ─────────────────────────────────────────────────────────────

def create_ordered_sale_document(
    user_id: str,
    user_email: str,
    owner_id: str,
    store_name: str,
    product_id: str,
    product_name: str,
    category: str,
    price_per_unit: float,
    quantity: int,
) -> dict:
    """
    Stored in 'ordered_sales'. Stays here until the owner
    injects it into a selected analytics dataset.
    """
    return {
        "order_id":           f"ORD-{uuid.uuid4().hex[:12].upper()}",
        "user_id":            user_id,
        "user_email":         user_email,
        "owner_id":           owner_id,
        "store_name":         store_name,
        "product_id":         product_id,
        "product_name":       product_name,
        "category":           category,
        "price_per_unit":     round(float(price_per_unit), 2),
        "quantity":           int(quantity),
        "total_price":        round(float(price_per_unit) * int(quantity), 2),
        "order_status":       "pending",           # pending | injected | rejected
        "ordered_at":         datetime.now(timezone.utc),
        "injected_dataset_id": None,
        "injected_at":        None,
    }


# ─────────────────────────────────────────────────────────────
# Dataset Documents  (metadata for each owner-uploaded CSV)
# ─────────────────────────────────────────────────────────────

def create_dataset_document(
    owner_id: str,
    dataset_name: str,
    file_path: str,
    row_count: int = 0,
) -> dict:
    """
    Metadata entry in the 'datasets' collection created whenever
    an owner uploads a CSV via the data upload endpoint.
    """
    return {
        "dataset_id":    f"DS-{uuid.uuid4().hex[:10].upper()}",
        "owner_id":      owner_id,
        "dataset_name":  dataset_name.strip(),
        "file_path":     file_path,
        "row_count":     row_count,
        "uploaded_at":   datetime.now(timezone.utc),
        "last_updated":  datetime.now(timezone.utc),
    }