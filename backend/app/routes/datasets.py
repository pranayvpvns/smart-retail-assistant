"""
routes/datasets.py
──────────────────
Owner dataset management:
  GET    /api/v1/datasets           — list owner's datasets
  POST   /api/v1/datasets/scan      — auto-discover & register CSVs already on disk
  DELETE /api/v1/datasets/<id>      — remove dataset record
"""
import os
from pathlib import Path

from flask import Blueprint, jsonify, g, request

from app.utils.auth_helpers import token_required, role_required
from app.services.dataset_service import (
    get_owner_datasets,
    delete_dataset,
    register_dataset,
)
from app.db.mongo import get_database

datasets_bp = Blueprint("datasets", __name__, url_prefix="/api/v1/datasets")


@datasets_bp.route("", methods=["GET"])
@token_required
@role_required("owner")
def list_datasets():
    """GET /api/v1/datasets — returns all datasets for the authenticated owner."""
    db       = get_database()
    store_id = g.current_user["store_id"]
    datasets = get_owner_datasets(store_id, db)
    return jsonify({"datasets": datasets, "count": len(datasets)}), 200


@datasets_bp.route("/scan", methods=["POST"])
@token_required
@role_required("owner")
def scan_and_register():
    """
    POST /api/v1/datasets/scan
    Walks data/owners/<store_id>/ and registers any CSV that isn't
    already in the datasets collection. Safe to call multiple times.
    """
    import pandas as pd
    import os

    db       = get_database()
    store_id = g.current_user["store_id"]

    # Always resolve absolute path — 2 levels up from routes/ lands in backend/
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_dir = Path(backend_dir) / "data" / "owners" / store_id
    if not data_dir.exists():
        return jsonify({"success": True, "registered": 0, "message": "No data directory found"}), 200

    registered = 0
    skipped    = 0
    errors     = []

    for csv_file in data_dir.glob("*.csv"):
        # Skip products.csv — it's the product catalog, not a sales dataset
        if csv_file.name.lower() == "products.csv":
            continue

        file_path = str(csv_file)
        # Already registered?
        existing = db["datasets"].find_one({"owner_id": store_id, "file_path": file_path})
        if existing:
            skipped += 1
            continue

        try:
            row_count = len(pd.read_csv(csv_file))
        except Exception:
            row_count = 0

        try:
            register_dataset(
                owner_id=store_id,
                dataset_name=csv_file.name,
                file_path=file_path,
                row_count=row_count,
                db=db,
            )
            registered += 1
        except Exception as exc:
            errors.append(f"{csv_file.name}: {exc}")

    return jsonify({
        "success":    True,
        "registered": registered,
        "skipped":    skipped,
        "errors":     errors,
        "message":    f"{registered} dataset(s) registered, {skipped} already known.",
    }), 200


@datasets_bp.route("/link", methods=["POST"])
@token_required
@role_required("owner")
def link_external_dataset():
    """
    POST /api/v1/datasets/link
    Body: { "file_path": "C:/Users/.../dataset.csv" }
    Registers an external file by its absolute path.
    """
    data = request.get_json()
    if not data or "file_path" not in data:
        return jsonify({"error": "Missing 'file_path' in request body"}), 400

    raw_path = data["file_path"].strip().strip('"').strip("'")
    if not raw_path:
        return jsonify({"error": "File path cannot be empty"}), 400

    # Ensure path is absolute or resolve it
    file_path = os.path.abspath(raw_path)
    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found at: {file_path}"}), 404

    if not file_path.lower().endswith(".csv"):
        return jsonify({"error": "Only CSV files can be linked"}), 415

    db       = get_database()
    store_id = g.current_user["store_id"]

    # Check if this exact file is already linked
    existing = db["datasets"].find_one({"owner_id": store_id, "file_path": file_path})
    if existing:
        return jsonify({"error": "This file is already registered as a dataset", "dataset_id": existing["dataset_id"]}), 409

    import pandas as pd
    try:
        row_count = len(pd.read_csv(file_path))
    except Exception as e:
        return jsonify({"error": f"Could not read CSV file: {str(e)}"}), 422

    try:
        dataset_status = register_dataset(
            owner_id=store_id,
            dataset_name=os.path.basename(file_path),
            file_path=file_path,
            row_count=row_count,
            db=db,
        )
        return jsonify({
            "success": True,
            "message": "Local file linked successfully",
            "dataset": dataset_status
        }), 201
    except Exception as e:
        return jsonify({"error": f"Failed to register dataset: {str(e)}"}), 500


@datasets_bp.route("/<dataset_id>", methods=["DELETE"])
@token_required
@role_required("owner")
def remove_dataset(dataset_id: str):
    """DELETE /api/v1/datasets/<dataset_id> — removes metadata record (CSV file kept)."""
    db     = get_database()
    result = delete_dataset(dataset_id, g.current_user["store_id"], db)
    return jsonify(result), 200 if result["success"] else 404
