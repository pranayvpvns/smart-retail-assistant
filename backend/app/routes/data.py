from flask import Blueprint, request, jsonify, g
from app.utils.auth_helpers import token_required
from app.utils.validators import allowed_file

from app.services.data_service import (
    process_and_store_csv,
    get_records,
    delete_records,
)

from app.services.dataset_service import register_dataset

from app.services.blob_service import (
    upload_bytes_to_blob,
    upload_dataframe_parquet,
)

from app.db.mongo import get_database

import pandas as pd


data_bp = Blueprint(
    "data",
    __name__,
    url_prefix="/api/v1/data"
)


@data_bp.route("/upload", methods=["POST"])
@token_required
def upload():

    if "file" not in request.files:
        return jsonify({
            "error": "No file part in the request"
        }), 400

    file = request.files["file"]

    original_filename = (
        file.filename or "uploaded_dataset.csv"
    )

    if original_filename == "":
        return jsonify({
            "error": "No file selected"
        }), 400

    if not allowed_file(original_filename):
        return jsonify({
            "error": "Only CSV files are accepted"
        }), 415

    file_bytes = file.read()

    if len(file_bytes) == 0:
        return jsonify({
            "error": "Uploaded file is empty"
        }), 400

    db = get_database()

    store_id = g.current_user["store_id"]

    # ─────────────────────────────────────
    # Upload RAW CSV to Azure Blob
    # ─────────────────────────────────────

    raw_blob = upload_bytes_to_blob(
        file_bytes=file_bytes,
        original_filename=original_filename,
        store_id=store_id,
    )

    # ─────────────────────────────────────
    # Process CSV
    # ─────────────────────────────────────

    report = process_and_store_csv(
        file_bytes=file_bytes,
        store_id=store_id,
        db=db,
    )

    if not report["success"]:

        return jsonify({
            "success": False,
            "message": (
                "Upload failed during "
                + report["stage"]
            ),
            "errors": report["errors"],
        }), 422

    # ─────────────────────────────────────
    # Clear old alerts
    # ─────────────────────────────────────

    db["alerts"].delete_many({
        "store_id": store_id
    })

    # ─────────────────────────────────────
    # Export Processed DataFrame
    # ─────────────────────────────────────

    records = list(
        db["sales_records"].find(
            {"store_id": store_id},
            {"_id": 0}
        )
    )

    processed_df = pd.DataFrame(records)

    # ─────────────────────────────────────
    # Upload STAGED Parquet
    # ─────────────────────────────────────

    staged_blob = upload_dataframe_parquet(
        df=processed_df,
        filename=original_filename,
        store_id=store_id,
    )

    # ─────────────────────────────────────
    # Register Dataset Metadata
    # ─────────────────────────────────────

    dataset_status = register_dataset(
        owner_id=store_id,
        dataset_name=original_filename,
        file_path=raw_blob["blob_url"],
        row_count=report["records_loaded"],
        db=db,
    )

    # ─────────────────────────────────────
    # Retrain ML Models
    # ─────────────────────────────────────

    retrain_status = _auto_retrain(store_id)

    return jsonify({

        "success": True,

        "message": (
            "File uploaded and processed "
            "successfully"
        ),

        "raw_blob": raw_blob,

        "staged_blob": staged_blob,

        "report": {

            "records_in_file":
                report["records_in_file"],

            "duplicates_removed":
                report["duplicates_removed"],

            "nulls_imputed":
                report["nulls_imputed"],

            "invalid_rows_dropped":
                report["invalid_rows_dropped"],

            "records_loaded":
                report["records_loaded"],
        },

        "dataset_registered":
            dataset_status,

        "models_retrained":
            retrain_status,

    }), 201


def _auto_retrain(store_id: str) -> dict:

    try:

        import sys
        import os

        project_root = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                ".."
            )
        )

        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from ml.train import run_training

        run_training(store_id)

        from app.services.forecast_service import reload_models

        from app.services.anomaly_service import (
            reload_models as reload_anomaly
        )

        reload_models(store_id=store_id)
        reload_anomaly(store_id=store_id)

        return {
            "success": True,
            "message": "Models retrained successfully"
        }

    except Exception as e:

        print(f"⚠️ Auto-retrain failed: {e}")

        return {
            "success": False,
            "error": str(e)
        }


@data_bp.route("/records", methods=["GET"])
@token_required
def records():

    page = int(
        request.args.get("page", 1)
    )

    limit = int(
        request.args.get("limit", 50)
    )

    limit = min(limit, 200)

    db = get_database()

    store_id = g.current_user["store_id"]

    result = get_records(
        store_id=store_id,
        db=db,
        page=page,
        limit=limit,
    )

    return jsonify(result), 200


@data_bp.route("/records", methods=["DELETE"])
@token_required
def delete():

    confirm = (
        request.args.get(
            "confirm",
            "false"
        ).lower() == "true"
    )

    db = get_database()

    store_id = g.current_user["store_id"]

    result = delete_records(
        store_id=store_id,
        db=db,
        confirm=confirm,
    )

    if not result["success"]:
        return jsonify(result), 400

    try:

        from app.services.forecast_service import (
            clear_models as clear_forecast
        )

        from app.services.anomaly_service import (
            clear_models as clear_anomaly
        )

        clear_forecast()

        clear_anomaly()

        db["alerts"].delete_many({
            "store_id": store_id
        })

        result["models_cleared"] = True

        result["alerts_cleared"] = True

    except Exception as e:

        print(f"⚠️ Model cleanup failed: {e}")

        result["models_cleared"] = False

    return jsonify(result), 200