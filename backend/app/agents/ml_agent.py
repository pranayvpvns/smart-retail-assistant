import os
import sys
import numpy as np
from datetime import datetime, timezone

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)
from app.config import get_settings
from app.services.forecast_service import (
    get_forecast,
    get_available_products,
)
from pymongo.database import Database

settings = get_settings()

def get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.2,
        max_tokens=1000,
    )

# ─────────────────────────────────────────────
# Product Name Resolver
# ─────────────────────────────────────────────
def _get_product_mapping(store_id: str, db: Database) -> dict:
    """Returns a map of {product_id: product_name} from the catalog."""
    products = list(db["products"].find({"store_id": store_id}, {"product_id": 1, "product_name": 1}))
    mapping = {p["product_id"]: p["product_name"] for p in products}
    return mapping

# ─────────────────────────────────────────────
# Forecast Context Builder
# ─────────────────────────────────────────────
def _get_forecast_context(store_id: str, days: int = 14) -> str:
    try:
        products = get_available_products(store_id)
    except Exception:
        return "Forecast models not trained yet."

    if not products:
        return "No trained forecast models found."

    season_map = {0: "Winter", 1: "Summer", 2: "Monsoon", 3: "Festive"}
    lines = []

    for product_id in products:
        try:
            result = get_forecast(product_id, store_id=store_id, days=days)
            forecast = result["forecast"]
            if not forecast: continue
            
            future_forecast = [r for r in forecast if r["predicted_sales"] > 0]
            if not future_forecast: continue

            product_name = future_forecast[0].get("product_name", product_id)
            total_predicted = sum(r["predicted_sales"] for r in future_forecast)
            peak = max(future_forecast, key=lambda x: x["predicted_sales"])
            
            # Trend calculation
            growth_pct = ((future_forecast[-1]["predicted_sales"] - future_forecast[0]["predicted_sales"]) / max(1, future_forecast[0]["predicted_sales"])) * 100
            trend = "stable"
            if growth_pct > 10: trend = "increasing"
            elif growth_pct < -10: trend = "decreasing"

            lines.append(f"- {product_name} ({product_id}): Total {total_predicted:.0f} units, Trend: {trend}, Peak: {peak['predicted_sales']:.0f} on {peak['date']}")
        except Exception:
            continue

    return "\n".join(lines) if lines else "No forecast data available."

# ─────────────────────────────────────────────
# Sales & Orders Context Builder
# ─────────────────────────────────────────────
def _get_recent_performance_context(store_id: str, db: Database) -> str:
    """
    Combines sales_records (confirmed sales) and ordered_sales (real-time intent).
    """
    mapping = _get_product_mapping(store_id, db)
    
    # 1. Confirmed Sales (last 30 days)
    sales = list(db["sales_records"].find({"store_id": store_id}).sort("date", -1).limit(40))
    sales_lines = []
    for s in sales:
        pid = s["product_id"]
        name = s.get("product_name") or mapping.get(pid) or pid
        sales_lines.append(f"  - {name} ({pid}) on {s['date']}: {int(s['quantity_sold'])} units, ₹{s['revenue']:,.2f}")
    
    sales_str = "Confirmed Sales Records:\n" + ("\n".join(sales_lines) if sales_lines else "  No sales records found.")

    # 2. Recent Marketplace Orders
    orders = list(db["ordered_sales"].find({"owner_id": store_id}).sort("ordered_at", -1).limit(15))
    order_lines = []
    for o in orders:
        status = o.get("order_status") or o.get("status", "unknown")
        pid = o.get("product_id") or o.get("vendor_product_id")
        name = o.get("product_name") or mapping.get(pid) or pid
        date = o["ordered_at"].strftime("%Y-%m-%d")
        order_lines.append(f"  - Order {o['order_id']}: {name} ({pid}) x{o['quantity']} | Status: {status} | Date: {date}")

    orders_str = "Recent Marketplace Orders:\n" + ("\n".join(order_lines) if order_lines else "  No orders found.")

    return f"{sales_str}\n\n{orders_str}"

# ─────────────────────────────────────────────
# Main ML Agent
# ─────────────────────────────────────────────
def run_ml_agent(query: str, store_id: str, db: Database) -> str:
    llm = get_llm()
    
    forecast_context = _get_forecast_context(store_id=store_id)
    performance_context = _get_recent_performance_context(store_id, db)
    
    # Get active alerts
    alerts = list(db["alerts"].find({"store_id": store_id}).sort("detected_at", -1).limit(10))
    alerts_str = "Recent Anomaly Alerts:\n" + ("\n".join([f"  - {a['severity'].upper()}: {a['product_name']} on {a['date']} (qty {a['quantity_sold']})" for a in alerts]) if alerts else "  No active alerts.")

    system_prompt = """You are an AI Retail Strategist. 
You analyze sales performance, demand forecasts, and order trends.

TERMINOLOGY:
- "Confirmed Sales" or "Injected Orders" ARE the same thing. They represent actual revenue and data that our AI uses for learning.
- "Pending Orders" are items buyers want but haven't been confirmed/injected into the dataset yet.

STRATEGY:
1. When asked about "changes" or "performance", always look at both the historical sales records AND the recent marketplace orders.
2. If an order is "injected", treat it as a confirmed sale.
3. Be specific about product names and dates.
4. If you see multiple IDs for the same product (e.g. P100 and PRD-...), treat them as the same product if the name is the same.
5. Keep your response concise (under 150 words) and business-focused.
"""

    user_prompt = f"""
QUESTION: {query}

CURRENT PERFORMANCE DATA:
{performance_context}

DEMAND FORECASTS (PROPHET):
{forecast_context}

{alerts_str}

Analyze the data and answer the question. If an order was recently confirmed (injected), highlight it as the latest sale.
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        return f"Error analyzing data: {str(e)}"