"""
dataset_service.py
──────────────────
Manages owner analytics datasets (metadata + CSV operations).

Responsibilities:
  • Register dataset when a CSV is uploaded
  • List datasets per owner
  • Append a sale row to a specific dataset CSV + update MongoDB sales_records
  • Trigger analytics refresh after injection
"""
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pymongo.database import Database

from app.models.db_models import create_dataset_document


# ── Registration ───────────────────────────────────────────────

def register_dataset(
    owner_id: str,
    dataset_name: str,
    file_path: str,
    row_count: int,
    db: Database,
) -> dict:
    """
    Called after a CSV upload succeeds. Upserts dataset metadata
    in the 'datasets' collection so the owner can reference it later.
    """
    existing = db["datasets"].find_one({"owner_id": owner_id, "file_path": file_path})
    if existing:
        db["datasets"].update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "dataset_name": dataset_name,
                "row_count":    row_count,
                "last_updated": datetime.now(timezone.utc),
            }},
        )
        return {"success": True, "dataset_id": existing["dataset_id"], "action": "updated"}

    doc = create_dataset_document(
        owner_id=owner_id,
        dataset_name=dataset_name,
        file_path=file_path,
        row_count=row_count,
    )
    db["datasets"].insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "dataset_id": doc["dataset_id"], "action": "created"}


def get_owner_datasets(owner_id: str, db: Database) -> list:
    """Returns all datasets belonging to an owner, newest first."""
    docs = list(
        db["datasets"]
        .find({"owner_id": owner_id}, {"_id": 0})
        .sort("uploaded_at", -1)
    )
    return [_serialize(d) for d in docs]


def delete_dataset(dataset_id: str, owner_id: str, db: Database) -> dict:
    """Removes dataset metadata (does NOT delete the CSV file)."""
    result = db["datasets"].delete_one({"dataset_id": dataset_id, "owner_id": owner_id})
    if result.deleted_count == 0:
        return {"success": False, "error": "Dataset not found or access denied"}
    return {"success": True}


# ── Sale Injection ─────────────────────────────────────────────

# Expected CSV columns — must match what the analytics pipeline reads
SALES_CSV_COLUMNS = [
    "date", "product_id", "product_name", "quantity_sold",
    "revenue", "store_id", "category", "cost", "stock_level",
]


def append_sale_to_dataset(
    dataset_id: str,
    owner_id: str,
    order: dict,         # ordered_sale document
    db: Database,
) -> dict:
    """
    Appends a sale row derived from an order into the chosen dataset CSV
    and upserts the matching sales_records entry in MongoDB.

    Called when owner selects a dataset and approves an order injection.

    Returns {"success": True, "dataset_id": ..., "csv_path": ...}
    """
    dataset = db["datasets"].find_one({"dataset_id": dataset_id, "owner_id": owner_id})
    if not dataset:
        return {"success": False, "error": "Dataset not found or access denied"}

    raw_path = dataset["file_path"]
    is_cloud = raw_path.startswith("http")
    
    # 1. Resolve Path
    if is_cloud:
        # For cloud datasets, we download to a temporary local file first
        from app.services.blob_service import download_blob_temp, upload_to_specific_blob
        try:
            # Extract blob name from URL
            parts = raw_path.split("/")
            blob_name = "/".join(parts[4:])
            local_tmp_path = download_blob_temp(blob_name)
            csv_path = Path(local_tmp_path)
        except Exception as exc:
            return {"success": False, "error": f"Failed to download cloud dataset: {exc}"}
    else:
        # Local filesystem path
        csv_path = Path(raw_path)
        if not csv_path.is_absolute():
            import os
            backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            csv_path = Path(backend_dir) / csv_path

        if not csv_path.exists():
            try:
                csv_path.parent.mkdir(parents=True, exist_ok=True)
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    import csv as _csv
                    _csv.DictWriter(f, fieldnames=SALES_CSV_COLUMNS).writeheader()
            except Exception:
                return {"success": False, "error": f"CSV file not found and could not be created at {csv_path}"}

    # ── Build sale row ──────────────────────────────────────────
    today      = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    revenue    = round(float(order.get("total_price") or order.get("total_amount") or 0), 2)
    quantity   = int(order.get("quantity") or 1)
    price_unit = round(float(order.get("price_per_unit") or 0), 2)

    product_id = order.get("product_id") or order.get("vendor_product_id")

    # Read current stock from products collection to record post-sale level
    prod = db["products"].find_one(
        {"product_id": product_id, "owner_id": owner_id},
        {"stock": 1},
    )
    stock_level = prod["stock"] if prod else 0

    sale_row = {
        "date":          today,
        "product_id":    product_id,
        "product_name":  order.get("product_name", "Unknown Product"),
        "quantity_sold": quantity,
        "revenue":       revenue,
        "store_id":      owner_id,
        "category":      order.get("category", "General"),
        "cost":          round(price_unit * 0.6, 2),   # estimate 60% cost if unknown
        "stock_level":   stock_level,
    }

    # ── Append to CSV ───────────────────────────────────────────
    try:
        _ensure_header(csv_path)
        
        # Check if file ends with newline to avoid 'same-row' append issues
        needs_newline = False
        if csv_path.exists() and csv_path.stat().st_size > 0:
            with open(csv_path, "rb") as f_binary:
                f_binary.seek(-1, 2)
                if f_binary.read(1) != b"\n":
                    needs_newline = True

        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            if needs_newline:
                f.write("\n")
            writer = csv.DictWriter(f, fieldnames=SALES_CSV_COLUMNS)
            writer.writerow(sale_row)
            
    except Exception as e:
        return {"success": False, "error": f"Failed to write to CSV: {str(e)}"}

    # ── Upsert MongoDB sales_records (Aggregate if same product on same day) ──
    db["sales_records"].update_one(
        filter={
            "date":       today,
            "product_id": sale_row["product_id"],
            "store_id":   owner_id,
        },
        update={
            "$inc": {
                "quantity_sold": quantity,
                "revenue":       revenue,
            },
            "$set": {
                "product_name":  sale_row["product_name"],
                "category":      sale_row["category"],
                "cost":          sale_row["cost"],
                "stock_level":   sale_row["stock_level"],
                "updated_at":    datetime.now(timezone.utc)
            }
        },
        upsert=True,
    )

    # ── Update dataset row_count ────────────────────────────────
    try:
        df = pd.read_csv(csv_path)
        new_count = len(df)
    except Exception:
        new_count = dataset.get("row_count", 0) + 1

    db["datasets"].update_one(
        {"_id": dataset["_id"]},
        {"$set": {
            "row_count":    new_count,
            "last_updated": datetime.now(timezone.utc),
        }},
    )

    # ── Upload back if cloud ───────────────────────────────────
    if is_cloud:
        from app.services.blob_service import upload_to_specific_blob
        success = upload_to_specific_blob(str(csv_path), raw_path)
        # Cleanup temp file
        try:
            import os
            os.remove(csv_path)
        except Exception:
            pass
            
        if not success:
            return {"success": False, "error": "Failed to re-upload updated dataset to cloud"}
            
    # ── Trigger Staged/Curated Refresh ────────────────────────
    try:
        _refresh_azure_pipeline(owner_id, dataset["dataset_name"], db)
    except Exception as e:
        print(f"⚠️ Pipeline refresh failed: {e}")

    return {
        "success":  True,
        "csv_path": str(csv_path) if not is_cloud else raw_path,
        "row_count": new_count,
    }


def _refresh_azure_pipeline(store_id: str, dataset_name: str, db: Database):
    """
    Refreshes the Staged and Curated Parquet files in Azure
    based on the current state of MongoDB sales_records.
    """
    import pandas as pd
    from app.services.blob_service import upload_dataframe_parquet
    from ml.preprocessing import is_holiday, encode_season

    # 1. Load from MongoDB
    records = list(db["sales_records"].find({"store_id": store_id}, {"_id": 0}))
    if not records:
        return
    
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])

    # 2. Update STAGED (Parquet)
    from app.services.blob_service import STAGED_CONTAINER
    upload_dataframe_parquet(
        df=df,
        filename=dataset_name,
        store_id=store_id,
        container=STAGED_CONTAINER
    )

    # 3. Add Features for CURATED
    df["is_weekend"] = df["date"].dt.dayofweek.isin([5, 6]).astype(int)
    df["is_holiday"] = df["date"].apply(is_holiday)
    df["season_encoded"] = df["date"].dt.month.apply(encode_season)

    # 4. Update CURATED (Parquet)
    from app.services.blob_service import CURATED_CONTAINER
    upload_dataframe_parquet(
        df=df,
        filename=dataset_name,
        store_id=store_id,
        container=CURATED_CONTAINER
    )
    print(f"🚀 Pipeline sync complete for {store_id} (Staged & Curated updated)")


# ── Helpers ────────────────────────────────────────────────────

def _ensure_header(path: Path) -> None:
    """Creates CSV with header if empty or missing."""
    if not path.exists() or path.stat().st_size == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=SALES_CSV_COLUMNS).writeheader()


def _serialize(doc: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in doc.items()}
