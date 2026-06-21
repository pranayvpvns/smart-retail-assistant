from flask import Blueprint, request, jsonify, g
from app.utils.auth_helpers import token_required
from app.db.mongo import get_database

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/v1/dashboard")


@dashboard_bp.route("/analytics", methods=["GET"])
@token_required
def analytics():
    """
    GET /api/v1/dashboard/analytics
    Returns aggregated KPIs and sales data for the analytics dashboard.
    Auth: Bearer token required
    """
    db = get_database()
    store_id = g.current_user["store_id"]
    collection = db["sales_records"]

    # ── Total Records ──
    total_records = collection.count_documents({"store_id": store_id})

    if total_records == 0:
        return jsonify({
            "total_revenue": 0,
            "total_records": 0,
            "total_orders": 0,
            "total_products_sold": 0,
            "total_products_tracked": 0,
            "total_inventory_products": db["products"].count_documents({"owner_id": store_id}),
            "top_category": "N/A",
            "active_alerts": 0,
            "sales_by_date": [],
            "sales_by_category": [],
            "sales_by_product": [],
            "top_products": [],
        }), 200

    # ── Fetch All Records for Aggregation ──
    records = list(collection.find({"store_id": store_id}))
    
    total_revenue = sum(r.get("revenue", 0) for r in records)
    total_products_sold = sum(r.get("quantity_sold", 0) for r in records)
    kpi = {"total_revenue": total_revenue, "total_products_sold": total_products_sold}

    # Force synchronization of records and orders as requested
    kpi["total_records"] = total_records
    kpi["total_orders"] = total_records 

    # ── Top Category by Revenue ──
    category_map = {}
    for r in records:
        cat = r.get("category") or "Unknown"
        if cat not in category_map:
            category_map[cat] = {"revenue": 0, "quantity": 0}
        category_map[cat]["revenue"] += r.get("revenue", 0)
        category_map[cat]["quantity"] += r.get("quantity_sold", 0)
    
    categories = [{"_id": k, "revenue": v["revenue"], "quantity": v["quantity"]} for k, v in category_map.items()]
    categories.sort(key=lambda x: x["revenue"], reverse=True)
    top_category = categories[0]["_id"] if categories else "N/A"

    # ── Sales by Date (for trend chart) ──
    date_map = {}
    for r in records:
        d = r.get("date")
        if not d: continue
        if d not in date_map:
            date_map[d] = {"revenue": 0, "quantity": 0}
        date_map[d]["revenue"] += r.get("revenue", 0)
        date_map[d]["quantity"] += r.get("quantity_sold", 0)
    
    sales_by_date = [{"_id": k, "revenue": v["revenue"], "quantity": v["quantity"]} for k, v in date_map.items()]
    sales_by_date.sort(key=lambda x: x["_id"])

    # ── Sales by Product (top sellers) ──
    product_map = {}
    for r in records:
        pid = r.get("product_id")
        if not pid: continue
        if pid not in product_map:
            product_map[pid] = {"name": r.get("product_name") or pid, "revenue": 0, "quantity": 0}
        product_map[pid]["revenue"] += r.get("revenue", 0)
        product_map[pid]["quantity"] += r.get("quantity_sold", 0)
    
    top_products = [{"_id": k, "name": v["name"], "revenue": v["revenue"], "quantity": v["quantity"]} for k, v in product_map.items()]
    top_products.sort(key=lambda x: x["revenue"], reverse=True)
    top_products = top_products[:10]

    # ── Total Products Tracked (Unique products in sales records) ──
    tracked_products_count = len(collection.distinct("product_id", {"store_id": store_id}))

    # ── Total Products in Catalog ──
    total_catalog_products = db["products"].count_documents({"owner_id": store_id})

    # ── Active Alerts Count ──
    alerts_count = db["alerts"].count_documents({"store_id": store_id, "acknowledged": False})

    return jsonify({
        "total_revenue": round(kpi.get("total_revenue", 0), 2),
        "total_records": kpi.get("total_records", 0),
        "total_orders": kpi.get("total_orders", 0),
        "total_products_sold": kpi.get("total_products_sold", 0),
        "total_products_tracked": tracked_products_count,
        "total_inventory_products": total_catalog_products,
        "top_category": top_category if top_category else "N/A",
        "active_alerts": alerts_count,
        "sales_by_date": [
            {"date": str(d["_id"]), "revenue": round(d["revenue"], 2), "quantity": d["quantity"]}
            for d in sales_by_date
        ],
        "sales_by_category": [
            {"category": c["_id"] or "Unknown", "revenue": round(c["revenue"], 2), "quantity": c["quantity"]}
            for c in categories
        ],
        "top_products": [
            {
                "product_id": p["_id"],
                "product_name": p.get("name") or p["_id"],
                "revenue": round(p["revenue"], 2),
                "quantity": p["quantity"]
            }
            for p in top_products
        ],
    }), 200


@dashboard_bp.route("/ai-recommendations", methods=["POST"])
@token_required
def ai_recommendations():
    """
    POST /api/v1/dashboard/ai-recommendations
    Generates AI business recommendations based on current data context.
    Auth: Bearer token required
    """
    db = get_database()
    store_id = g.current_user["store_id"]

    try:
        from app.services.agent_service import run_agent
        result = run_agent(
            query="Based on the current sales trends, forecasts, and any anomalies, "
                  "give me 3-4 actionable business recommendations for my store. "
                  "Cover restocking, promotions, and risk areas.",
            store_id=store_id,
            db=db,
        )
        return jsonify({
            "recommendations": result.get("response", ""),
            "agents_used": result.get("agents_used", []),
            "intent": result.get("intent", ""),
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to generate recommendations: {str(e)}"}), 500


@dashboard_bp.route("/insights", methods=["POST"])
@token_required
def ai_insights():
    """
    POST /api/v1/dashboard/insights
    Synthesizes structured AI business insights from all ML signals
    (forecasts, anomalies, sales data). Returns categorized, prioritized
    insights with executive summary.
    Auth: Bearer token required
    """
    db = get_database()
    store_id = g.current_user["store_id"]

    try:
        from app.services.insight_service import synthesize_insights
        result = synthesize_insights(store_id=store_id, db=db)
        return jsonify(result), 200 if result.get("success") else 422
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Insight synthesis failed: {str(e)}",
            "insights": [],
            "executive_summary": "",
        }), 500
