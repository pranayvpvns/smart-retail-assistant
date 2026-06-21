import os
import sys

from flask import Blueprint, request, jsonify

CURRENT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

BACKEND_DIR = os.path.dirname(
    os.path.dirname(CURRENT_DIR)
)

PROJECT_ROOT = os.path.dirname(
    BACKEND_DIR
)

sys.path.insert(0, PROJECT_ROOT)

from data_pipeline.pyspark_pipeline import (
    run_pipeline
)

pipeline_bp = Blueprint(
    "pipeline",
    __name__,
    url_prefix="/api/v1/pipeline"
)


@pipeline_bp.route(
    "/run-etl",
    methods=["POST"]
)
def run_etl():

    try:

        data = request.get_json()

        blob_name = data.get("blob_name")

        store_id = data.get("store_id")
        print("BLOB NAME:", blob_name)
        print("STORE ID:", store_id)

        if not blob_name:

            return jsonify({
                "success": False,
                "error": "blob_name is required"
            }), 400

        if not store_id:

            return jsonify({
                "success": False,
                "error": "store_id is required"
            }), 400

        result = run_pipeline(
            blob_name=blob_name,
            store_id=store_id,
        )

        return jsonify(result), 200

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500