"""
csv_update_service.py
─────────────────────
Thread-safe appending of new sale rows into the owner's CSV file
on disk whenever an order is placed, keeping the analytics dataset
and MongoDB sales_records in sync.
"""
import os
import threading
import csv
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings

settings = get_settings()

# Global lock map: one lock per store (owner) CSV file
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _get_lock(store_id: str) -> threading.Lock:
    """Returns (or creates) a per-store write lock."""
    with _locks_guard:
        if store_id not in _locks:
            _locks[store_id] = threading.Lock()
        return _locks[store_id]


def get_owner_csv_path(store_id: str) -> Path:
    """
    Resolves the CSV file path for a given owner.
    Files are stored at: <project_root>/data/owners/<store_id>/sales.csv
    """
    base = Path(settings.vector_db_path).resolve().parent  # project_root/db
    csv_dir = base.parent / "data" / "owners" / store_id
    csv_dir.mkdir(parents=True, exist_ok=True)
    return csv_dir / "sales.csv"


# Expected CSV columns — matches the analytics pipeline schema
CSV_COLUMNS = [
    "date",
    "product_id",
    "product_name",
    "quantity_sold",
    "revenue",
    "store_id",
    "category",
    "cost",
    "stock_level",
]


def ensure_csv_header(csv_path: Path) -> None:
    """Creates the CSV with a header row if it does not yet exist."""
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()


def append_sale_row(
    store_id: str,
    product_id: str,
    product_name: str,
    category: str,
    quantity_sold: int,
    revenue: float,
    cost: float,
    new_stock_level: int,
) -> dict:
    """
    Appends a single sale row to the owner's CSV file.
    Thread-safe — acquires a per-store lock before writing.

    Returns {"success": True, "csv_path": str} or {"success": False, "error": str}.
    """
    csv_path = get_owner_csv_path(store_id)
    lock     = _get_lock(store_id)

    try:
        with lock:
            ensure_csv_header(csv_path)

            row = {
                "date":          datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "product_id":    product_id,
                "product_name":  product_name,
                "quantity_sold": quantity_sold,
                "revenue":       round(revenue, 2),
                "store_id":      store_id,
                "category":      category,
                "cost":          round(cost, 2),
                "stock_level":   new_stock_level,
            }

            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writerow(row)

        return {"success": True, "csv_path": str(csv_path)}

    except Exception as exc:
        return {"success": False, "error": str(exc)}


def sync_csv_to_mongo(store_id: str, db) -> dict:
    """
    Reads the owner's on-disk CSV and upserts all rows into MongoDB
    sales_records — useful after a manual CSV edit or bulk restore.
    """
    csv_path = get_owner_csv_path(store_id)
    if not csv_path.exists():
        return {"success": False, "error": "No CSV file found for this store"}

    import pandas as pd
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        return {"success": False, "error": f"CSV read error: {exc}"}

    if df.empty:
        return {"success": True, "synced": 0}

    df["store_id"] = store_id
    records  = df.to_dict(orient="records")
    col      = db["sales_records"]
    upserted = 0

    for rec in records:
        result = col.update_one(
            filter={
                "date":       rec.get("date"),
                "product_id": rec.get("product_id"),
                "store_id":   store_id,
            },
            update={"$set": rec},
            upsert=True,
        )
        if result.upserted_id or result.modified_count:
            upserted += 1

    return {"success": True, "synced": upserted}
