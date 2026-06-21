import sys
import os

# Ensure data_pipeline is importable from backend/app/services/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

PROJECT_ROOT = os.path.abspath(
    os.path.join(CURRENT_DIR, "..", "..", "..")
)

BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

from pymongo.database import Database
from data_pipeline.ingest import ingest_csv
from data_pipeline.clean import clean_dataframe
from data_pipeline.transform import transform_to_timeseries


def process_and_store_csv(
    file_bytes: bytes,
    store_id: str,
    db: Database,
) -> dict:
    """
    Full pipeline: validate → clean → transform → store in MongoDB.

    Returns a validation + load report dict.
    """

    # ── Step 1: Ingest & Validate ─────────────────────────────
    raw_df, ingest_errors = ingest_csv(file_bytes)

    if ingest_errors:
        return {
            "success": False,
            "stage": "ingestion",
            "errors": ingest_errors,
            "records_loaded": 0,
        }

    # ── Step 2: Clean ─────────────────────────────────────────
    clean_df, clean_report = clean_dataframe(raw_df)

    if clean_df.empty:
        return {
            "success": False,
            "stage": "cleaning",
            "errors": ["No valid records remained after cleaning"],
            "records_loaded": 0,
            "cleaning_report": clean_report,
        }

    # ── Step 3: Stamp store_id from auth (override CSV value) ─
    # Always use the authenticated user's store_id for isolation
    clean_df["store_id"] = store_id

    # ── Step 4: Transform to time-series format ───────────────
    ts_df = transform_to_timeseries(clean_df)

    # ── Step 5: Store in MongoDB ──────────────────────────────
    records = ts_df.to_dict(orient="records")

    collection = db["sales_records"]

    # Upsert each record using composite key to avoid duplicates
    # on re-uploads of the same dataset
    upserted = 0
    for record in records:
        result = collection.update_one(
            filter={
                "date": record["date"],
                "product_id": record["product_id"],
                "store_id": record["store_id"],
            },
            update={"$set": record},
            upsert=True,
        )
        if result.upserted_id or result.modified_count:
            upserted += 1

    return {
        "success": True,
        "stage": "complete",
        "errors": [],
        "records_in_file": clean_report["rows_before"],
        "duplicates_removed": clean_report["duplicates_removed"],
        "nulls_imputed": clean_report["nulls_imputed"],
        "invalid_rows_dropped": clean_report["invalid_rows_dropped"],
        "records_loaded": upserted,
    }


def get_records(store_id: str, db: Database, page: int = 1, limit: int = 50) -> dict:
    """
    Fetches paginated sales records for a store.
    Always scoped to the authenticated store_id.
    """
    collection = db["sales_records"]
    skip = (page - 1) * limit

    total = collection.count_documents({"store_id": store_id})
    records = list(
        collection.find(
            {"store_id": store_id},
            {"_id": 0},          # exclude MongoDB _id from response
        )
        .sort("date", -1)
        .skip(skip)
        .limit(limit)
    )

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "records": records,
    }


def delete_records(store_id: str, db: Database, confirm: bool = False) -> dict:
    """
    Deletes all sales records for a store.
    Requires confirm=True to prevent accidental deletion.
    """
    if not confirm:
        return {
            "success": False,
            "error": "Pass confirm=true to delete all records",
        }

    result = db["sales_records"].delete_many({"store_id": store_id})
    return {
        "success": True,
        "records_deleted": result.deleted_count,
    }