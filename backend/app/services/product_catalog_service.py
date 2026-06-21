"""
product_catalog_service.py
──────────────────────────
Standalone product management system (INDEPENDENT from analytics datasets).

Owner CRUD:
  add_product / update_product / delete_product / get_owner_products

Marketplace browsing:
  get_marketplace_products / get_product_detail / get_categories

CSV sync:
  sync_products_csv  ← writes data/owners/<store_id>/products.csv
"""
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from pymongo.database import Database

from app.models.db_models import create_product_document


# ── CSV helpers ────────────────────────────────────────────────

PRODUCTS_CSV_COLUMNS = [
    "product_id", "owner_id", "store_name", "product_name",
    "category", "price", "cost", "stock", "description", "created_at",
]


def _products_csv_path(store_id: str) -> Path:
    base = Path(os.environ.get("DATA_DIR", "data")) / "owners" / store_id
    base.mkdir(parents=True, exist_ok=True)
    return base / "products.csv"


def sync_products_csv(store_id: str, db: Database) -> None:
    """Rewrites products.csv from MongoDB for this owner (full sync)."""
    products = list(db["products"].find({"owner_id": store_id}, {"_id": 0}))
    path = _products_csv_path(store_id)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PRODUCTS_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)


# ── Owner CRUD ─────────────────────────────────────────────────

def add_product(owner_id: str, store_name: str, data: dict, db: Database) -> dict:
    """
    Creates a product in MongoDB + syncs products.csv.
    data keys: product_name, category, price, stock, description, image_url, cost
    """
    required = ["product_name", "price"]
    for field in required:
        if not data.get(field):
            return {"success": False, "error": f"'{field}' is required"}

    doc = create_product_document(
        owner_id=owner_id,
        store_name=store_name,
        product_name=data["product_name"],
        category=data.get("category", "General"),
        price=float(data["price"]),
        stock=int(data.get("stock", 0)),
        description=data.get("description", ""),
        image_url=data.get("image_url", ""),
        cost=float(data.get("cost", 0)),
    )
    db["products"].insert_one(doc)
    doc.pop("_id", None)
    sync_products_csv(owner_id, db)
    return {"success": True, "product": _serialize(doc)}


def update_product(product_id: str, owner_id: str, updates: dict, db: Database) -> dict:
    """Owner updates their own product. Allowed fields whitelist."""
    allowed = {"product_name", "category", "price", "stock", "description", "image_url", "cost"}
    safe = {k: v for k, v in updates.items() if k in allowed}
    if not safe:
        return {"success": False, "error": "No valid fields to update"}

    if "price" in safe:
        safe["price"] = round(float(safe["price"]), 2)
    if "cost" in safe:
        safe["cost"] = round(float(safe["cost"]), 2)
    if "stock" in safe:
        safe["stock"] = max(0, int(safe["stock"]))

    safe["updated_at"] = datetime.now(timezone.utc)

    result = db["products"].update_one(
        {"product_id": product_id, "owner_id": owner_id},
        {"$set": safe},
    )
    if result.matched_count == 0:
        return {"success": False, "error": "Product not found or access denied"}

    sync_products_csv(owner_id, db)
    return {"success": True, "updated": {k: v for k, v in safe.items() if k != "updated_at"}}


def delete_product(product_id: str, owner_id: str, db: Database) -> dict:
    """Deletes product from MongoDB + resyncs CSV."""
    result = db["products"].delete_one({"product_id": product_id, "owner_id": owner_id})
    if result.deleted_count == 0:
        return {"success": False, "error": "Product not found or access denied"}
    sync_products_csv(owner_id, db)
    return {"success": True}


def get_owner_products(owner_id: str, db: Database) -> list:
    """Returns all products belonging to an owner."""
    return [_serialize(p) for p in db["products"].find({"owner_id": owner_id}, {"_id": 0})]


# ── Marketplace Browsing ───────────────────────────────────────

def get_marketplace_products(
    db: Database,
    search: str = "",
    category: str = "",
    page: int = 1,
    limit: int = 20,
    owner_id: str = "",
) -> dict:
    """Paginated product listing for buyer marketplace."""
    query: dict = {}
    if search:
        query["product_name"] = {"$regex": search, "$options": "i"}
    if category:
        query["category"] = {"$regex": f"^{_re_escape(category)}$", "$options": "i"}
    if owner_id:
        query["owner_id"] = owner_id

    total = db["products"].count_documents(query)
    skip  = (page - 1) * limit

    products = list(
        db["products"]
        .find(query, {"_id": 0, "cost": 0, "owner_id": 0})  # hide margin & owner_id
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return {
        "total":    total,
        "page":     page,
        "limit":    limit,
        "products": [_serialize(p) for p in products],
    }


def get_product_detail(product_id: str, db: Database) -> dict | None:
    """Single product detail — for buyers."""
    p = db["products"].find_one({"product_id": product_id}, {"_id": 0, "cost": 0})
    return _serialize(p) if p else None


def get_categories(db: Database) -> list:
    return sorted(db["products"].distinct("category"))


# ── Bulk CSV Import ────────────────────────────────────────────

# Accepted column aliases (user-friendly → internal key)
_COL_ALIASES: dict[str, str] = {
    "name":         "product_name",
    "product":      "product_name",
    "product name": "product_name",
    "item":         "product_name",
    "item name":    "product_name",
    "cat":          "category",
    "type":         "category",
    "unit price":   "price",
    "selling price":"price",
    "mrp":          "price",
    "rate":         "price",
    "cogs":         "cost",
    "unit cost":    "cost",
    "purchase price":"cost",
    "qty":          "stock",
    "quantity":     "stock",
    "inventory":    "stock",
    "stock quantity":"stock",
    "desc":         "description",
    "details":      "description",
    "image":        "image_url",
    "img":          "image_url",
    "photo":        "image_url",
    "img url":      "image_url",
}

IMPORT_CSV_TEMPLATE_COLUMNS = [
    "product_name", "category", "price", "cost", "stock", "description", "image_url",
]

IMPORT_CSV_TEMPLATE_SAMPLE = [
    {
        "product_name": "Example Sneakers",
        "category":     "Footwear",
        "price":        "2499",
        "cost":         "1200",
        "stock":        "50",
        "description":  "Premium running shoes",
        "image_url":    "",
    },
]


def import_products_from_csv(
    owner_id: str,
    store_name: str,
    file_obj,               # file-like object (from Flask request.files)
    db: Database,
    mode: str = "upsert",  # "upsert" | "insert_new"
) -> dict:
    """
    Bulk-import products from a CSV file.

    Columns (flexible, uses alias map):
        product_name* | category | price* | cost | stock | description | image_url

    mode="upsert"      → update existing (matched by product_name+owner_id) or create
    mode="insert_new"  → skip rows whose product_name already exists

    Returns:
        { success, created, updated, skipped, failed, errors: [...] }
    """
    import io
    import pandas as pd

    errors:  list[str] = []
    created  = updated = skipped = failed = 0

    # ── Read CSV ───────────────────────────────────────────────
    try:
        raw = file_obj.read()
        # Try UTF-8 then latin-1
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("latin-1")

        df = pd.read_csv(io.StringIO(content))
    except Exception as exc:
        return {"success": False, "error": f"Could not read CSV: {exc}"}

    if df.empty:
        return {"success": False, "error": "CSV file is empty"}

    # ── Normalise column names ─────────────────────────────────
    df.columns = [str(c).strip().lower() for c in df.columns]
    rename_map = {}
    for col in df.columns:
        canonical = _COL_ALIASES.get(col, col)
        if canonical != col:
            rename_map[col] = canonical
    if rename_map:
        df.rename(columns=rename_map, inplace=True)

    # Required columns
    if "product_name" not in df.columns:
        return {"success": False, "error": "CSV must contain a 'product_name' column"}
    if "price" not in df.columns:
        return {"success": False, "error": "CSV must contain a 'price' column"}

    # Drop completely blank rows
    df.dropna(subset=["product_name"], inplace=True)
    df["product_name"] = df["product_name"].astype(str).str.strip()
    df = df[df["product_name"] != ""]

    # ── Process each row ───────────────────────────────────────
    ops = []          # bulk write operations

    for idx, row in df.iterrows():
        row_num = idx + 2   # 1-indexed + header

        try:
            price = float(str(row.get("price", "0")).replace(",", "") or "0")
            cost  = float(str(row.get("cost",  "0")).replace(",", "") or "0")
            stock = int(float(str(row.get("stock", "0")).replace(",", "") or "0"))
        except (ValueError, TypeError) as exc:
            errors.append(f"Row {row_num}: invalid number — {exc}")
            failed += 1
            continue

        product_name = str(row["product_name"]).strip()
        category     = str(row.get("category", "General") or "General").strip()
        description  = str(row.get("description", "") or "").strip()
        image_url    = str(row.get("image_url",  "") or "").strip()

        existing = db["products"].find_one(
            {"owner_id": owner_id, "product_name": {"$regex": f"^{_re_escape(product_name)}$", "$options": "i"}}
        )

        if existing:
            if mode == "insert_new":
                skipped += 1
                continue
            # upsert — update existing
            db["products"].update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "category":    category,
                    "price":       round(price, 2),
                    "cost":        round(cost,  2),
                    "stock":       max(0, stock),
                    "description": description,
                    "image_url":   image_url,
                    "updated_at":  datetime.now(timezone.utc),
                }},
            )
            updated += 1
        else:
            doc = create_product_document(
                owner_id=owner_id,
                store_name=store_name,
                product_name=product_name,
                category=category,
                price=price,
                stock=stock,
                description=description,
                image_url=image_url,
                cost=cost,
            )
            db["products"].insert_one(doc)
            created += 1

    # ── Sync products.csv ──────────────────────────────────────
    if created + updated > 0:
        sync_products_csv(owner_id, db)

    return {
        "success": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed":  failed,
        "total_rows": created + updated + skipped + failed,
        "errors":  errors[:20],   # cap at 20 error messages
    }


def generate_products_csv_template() -> str:
    """Returns a CSV string for the downloadable template."""
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=IMPORT_CSV_TEMPLATE_COLUMNS)
    writer.writeheader()
    writer.writerows(IMPORT_CSV_TEMPLATE_SAMPLE)
    return buf.getvalue()


# ── Helpers ────────────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    out = {}
    for k, v in doc.items():
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def _re_escape(s: str) -> str:
    special = r"\.^$*+?{}[]|()"
    return "".join(f"\\{c}" if c in special else c for c in s)
