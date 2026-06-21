from flask import Blueprint, request, jsonify, g
from app.utils.auth_helpers import token_required
from app.services.anomaly_service import (
    run_anomaly_detection,
    get_alerts
)
from app.db.mongo import get_database

anomaly_bp = Blueprint(
    "anomaly",
    __name__,
    url_prefix="/api/v1/anomaly"
)


@anomaly_bp.route("/alerts", methods=["GET"])
@token_required
def alerts():
    """
    GET /api/v1/anomaly/alerts
    Optional Query Params:
        severity=warning|critical

    Returns anomaly alerts for current store.
    """

    severity = request.args.get("severity")

    if severity and severity not in ("warning", "critical"):
        return jsonify({
            "success": False,
            "error": "severity must be 'warning' or 'critical'"
        }), 400

    db = get_database()

    store_id = g.current_user["store_id"]

    alerts_result = get_alerts(
        store_id=store_id,
        db=db,
        severity=severity
    )

    return jsonify({
        "success": True,
        "count": len(alerts_result),
        "alerts": alerts_result
    }), 200


@anomaly_bp.route("/run", methods=["POST"])
@token_required
def run_detection():
    """
    POST /api/v1/anomaly/run

    Triggers anomaly detection manually
    for current store data.
    """

    db = get_database()

    store_id = g.current_user["store_id"]

    try:

        result = run_anomaly_detection(
            store_id=store_id,
            db=db
        )

        if not result["success"]:
            return jsonify(result), 400

        return jsonify(result), 200

    except FileNotFoundError as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 503

    except Exception as e:

        return jsonify({
            "success": False,
            "error": f"Anomaly detection failed: {str(e)}"
        }), 500