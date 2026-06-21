"""
AI Insight Synthesis Service
─────────────────────────────────────────────────────────────
Collects ALL ML signals (forecasts, anomalies, sales stats)
and uses LLM to produce structured, categorized business
insights — translating raw ML outputs into actionable
business language.

Each insight contains:
  - category   : inventory | demand | revenue | anomaly | operations
  - priority   : critical | high | medium | low
  - title      : short headline
  - description: business-language explanation
  - action     : concrete recommended action
  - products   : affected product IDs
  - confidence : 0–100 confidence score
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pymongo.database import Database
import pandas as pd

from app.config import get_settings
from app.services.forecast_service import get_forecast, get_available_products

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────
# LLM Instance (higher token limit for structured output)
# ─────────────────────────────────────────────────────────────

def _get_synthesis_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.3,
        max_tokens=2000,
    )


# ─────────────────────────────────────────────────────────────
# Signal Collectors
# ─────────────────────────────────────────────────────────────

def _collect_forecast_signals(days: int = 14) -> dict:
    """
    Gathers forecast data for every trained product.
    Returns structured signals the LLM can reason over.
    """
    try:
        products = get_available_products()
    except (FileNotFoundError, Exception):
        return {"available": False, "products": []}

    if not products:
        return {"available": False, "products": []}

    product_signals = []
    for pid in products:
        try:
            result = get_forecast(pid, days=days)
            forecast = result["forecast"]
            predicted_values = [r["predicted_sales"] for r in forecast]
            total = sum(predicted_values)
            avg_daily = total / len(forecast) if forecast else 0
            peak = max(forecast, key=lambda x: x["predicted_sales"])
            low = min(forecast, key=lambda x: x["predicted_sales"])

            # Detect trend direction
            first_half = predicted_values[:len(predicted_values)//2]
            second_half = predicted_values[len(predicted_values)//2:]
            first_avg = sum(first_half) / len(first_half) if first_half else 0
            second_avg = sum(second_half) / len(second_half) if second_half else 0
            trend_pct = ((second_avg - first_avg) / max(first_avg, 1)) * 100

            # Detect volatility (coefficient of variation)
            import statistics
            std_dev = statistics.stdev(predicted_values) if len(predicted_values) > 1 else 0
            volatility = (std_dev / max(avg_daily, 1)) * 100

            # Weekend vs weekday demand gap
            weekend_sales = [r["predicted_sales"] for r in forecast if r.get("is_weekend")]
            weekday_sales = [r["predicted_sales"] for r in forecast if not r.get("is_weekend")]
            weekend_avg = sum(weekend_sales) / max(len(weekend_sales), 1)
            weekday_avg = sum(weekday_sales) / max(len(weekday_sales), 1)

            product_signals.append({
                "product_id": pid,
                "total_predicted": round(total, 1),
                "avg_daily": round(avg_daily, 1),
                "peak_day": peak["date"],
                "peak_qty": round(peak["predicted_sales"], 1),
                "lowest_day": low["date"],
                "lowest_qty": round(low["predicted_sales"], 1),
                "trend_pct": round(trend_pct, 1),
                "trend_direction": "rising" if trend_pct > 5 else ("falling" if trend_pct < -5 else "stable"),
                "volatility_pct": round(volatility, 1),
                "weekend_avg": round(weekend_avg, 1),
                "weekday_avg": round(weekday_avg, 1),
            })
        except Exception as e:
            logger.warning(f"Forecast signal failed for {pid}: {e}")

    return {"available": True, "products": product_signals}


def _collect_anomaly_signals(store_id: str, db: Database) -> dict:
    """
    Gathers anomaly alerts and computes summary statistics.
    """
    alerts = list(
        db["alerts"]
        .find({"store_id": store_id}, {"_id": 0})
        .sort("detected_at", -1)
        .limit(50)
    )

    if not alerts:
        return {"available": False, "total": 0, "alerts": []}

    critical = [a for a in alerts if a.get("severity") == "critical"]
    warnings = [a for a in alerts if a.get("severity") == "warning"]

    # Group by product
    product_alerts = {}
    for a in alerts:
        pid = a.get("product_id", "unknown")
        if pid not in product_alerts:
            product_alerts[pid] = {"critical": 0, "warning": 0, "details": []}
        if a.get("severity") == "critical":
            product_alerts[pid]["critical"] += 1
        else:
            product_alerts[pid]["warning"] += 1
        product_alerts[pid]["details"].append({
            "date": a.get("date", ""),
            "qty_sold": a.get("quantity_sold", 0),
            "avg_qty": a.get("average_quantity", 0),
            "deviation_pct": a.get("deviation_percent", 0),
            "score": a.get("anomaly_score", 0),
            "message": a.get("message", ""),
        })

    # Format for LLM
    product_summaries = []
    for pid, info in product_alerts.items():
        product_summaries.append({
            "product_id": pid,
            "critical_count": info["critical"],
            "warning_count": info["warning"],
            "latest_alerts": info["details"][:3],  # top 3 per product
        })

    return {
        "available": True,
        "total": len(alerts),
        "critical_count": len(critical),
        "warning_count": len(warnings),
        "by_product": product_summaries,
    }


def _collect_sales_signals(store_id: str, db: Database) -> dict:
    """
    Gathers historical sales summary stats from MongoDB.
    """
    records = list(
        db["sales_records"].find({"store_id": store_id}, {"_id": 0})
    )

    if not records:
        return {"available": False}

    df = pd.DataFrame(records)
    df["quantity_sold"] = pd.to_numeric(df["quantity_sold"], errors="coerce")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")

    total_revenue = float(df["revenue"].sum())
    total_units = int(df["quantity_sold"].sum())
    unique_products = df["product_id"].nunique()

    # Top products by revenue
    top_by_revenue = (
        df.groupby("product_id")["revenue"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
    )

    # Bottom products by revenue
    bottom_by_revenue = (
        df.groupby("product_id")["revenue"]
        .sum()
        .sort_values(ascending=True)
        .head(5)
    )

    # Low stock products
    low_stock = []
    if "stock_level" in df.columns:
        low_df = df[df["stock_level"] < 20][["product_id", "product_name", "stock_level"]]
        low_df = low_df.drop_duplicates("product_id")
        low_stock = low_df.to_dict("records")

    # Category breakdown
    category_revenue = {}
    if "category" in df.columns:
        category_revenue = (
            df.groupby("category")["revenue"]
            .sum()
            .sort_values(ascending=False)
            .to_dict()
        )

    # Date range
    date_range = f"{df['date'].min()} to {df['date'].max()}"

    return {
        "available": True,
        "date_range": date_range,
        "total_revenue": round(total_revenue, 2),
        "total_units": total_units,
        "unique_products": unique_products,
        "top_products": {str(k): round(float(v), 2) for k, v in top_by_revenue.items()},
        "bottom_products": {str(k): round(float(v), 2) for k, v in bottom_by_revenue.items()},
        "low_stock": low_stock[:5],
        "category_revenue": {str(k): round(float(v), 2) for k, v in category_revenue.items()},
    }


# ─────────────────────────────────────────────────────────────
# LLM Synthesis
# ─────────────────────────────────────────────────────────────

SYNTHESIS_SYSTEM_PROMPT = """You are an AI Business Insight Synthesizer for a retail store.

Your job is to analyze raw ML signals (demand forecasts, anomaly detection results, sales statistics) and translate them into clear, structured business insights that a non-technical store owner can immediately understand and act on.

You MUST return ONLY valid JSON — no markdown, no code fences, no explanation outside the JSON.

Return a JSON object with this exact structure:
{
  "executive_summary": "2-3 sentence overview of the store's current situation and most urgent priorities",
  "insights": [
    {
      "category": "inventory|demand|revenue|anomaly|operations",
      "priority": "critical|high|medium|low",
      "title": "Short headline (max 10 words)",
      "description": "Business-language explanation of what the ML signals show (2-3 sentences). No jargon. Explain WHY this matters to the store owner.",
      "action": "One specific, concrete action the store owner should take NOW.",
      "products": ["list", "of", "affected", "product_ids"],
      "metric_label": "Key Metric",
      "metric_value": "The key number (e.g. '₹45,000' or '+23%' or '5 units')",
      "confidence": 85
    }
  ]
}

Rules:
- Generate 4-8 insights, prioritized by business impact
- Always put critical/high priority items first
- Use ₹ for currency
- Use specific numbers — never vague language
- Each insight must have a DIFFERENT, concrete action
- "confidence" is 0-100, reflecting how confident the ML data supports this insight
- For "metric_value", use the single most impactful number for this insight
- Categories explained:
  - inventory: stock levels, restocking needs, overstock risks
  - demand: forecast trends, seasonal shifts, demand spikes/drops
  - revenue: revenue patterns, margin opportunities, underperformers
  - anomaly: unusual patterns, sales spikes/drops that need attention
  - operations: weekend/weekday patterns, staffing implications
"""


def synthesize_insights(store_id: str, db: Database) -> dict:
    """
    Main entry point: collects all ML signals, synthesizes structured
    business insights via LLM, and returns the result.
    """
    # ── Step 1: Collect all signals in parallel ───────────────
    forecast_signals = _collect_forecast_signals(days=14)
    anomaly_signals = _collect_anomaly_signals(store_id, db)
    sales_signals = _collect_sales_signals(store_id, db)

    # Check if we have any data to work with
    if not sales_signals.get("available"):
        return {
            "success": False,
            "error": "No sales data available. Upload data first.",
            "insights": [],
            "executive_summary": "",
        }

    # ── Step 2: Build context for LLM ─────────────────────────
    context_parts = []

    context_parts.append("=== SALES DATA SUMMARY ===")
    context_parts.append(json.dumps(sales_signals, indent=2, default=str))

    if forecast_signals.get("available"):
        context_parts.append("\n=== 14-DAY DEMAND FORECASTS ===")
        context_parts.append(json.dumps(forecast_signals["products"], indent=2, default=str))
    else:
        context_parts.append("\n=== FORECASTS: Not available (models not trained) ===")

    if anomaly_signals.get("available"):
        context_parts.append("\n=== ANOMALY DETECTION RESULTS ===")
        context_parts.append(json.dumps({
            "total_alerts": anomaly_signals["total"],
            "critical": anomaly_signals["critical_count"],
            "warnings": anomaly_signals["warning_count"],
            "by_product": anomaly_signals["by_product"],
        }, indent=2, default=str))
    else:
        context_parts.append("\n=== ANOMALIES: No alerts detected ===")

    full_context = "\n".join(context_parts)

    # ── Step 3: LLM synthesis ─────────────────────────────────
    llm = _get_synthesis_llm()

    user_prompt = f"""Analyze these ML signals and generate structured business insights:

{full_context}

Return ONLY the JSON object with executive_summary and insights array. No other text."""

    messages = [
        SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    try:
        response = llm.invoke(messages)
        raw_content = response.content.strip()

        # Strip markdown code fences if present
        if raw_content.startswith("```"):
            raw_content = raw_content.split("\n", 1)[1]  # remove first line
            if raw_content.endswith("```"):
                raw_content = raw_content[:-3].strip()

        parsed = json.loads(raw_content)

        # Validate structure
        insights = parsed.get("insights", [])
        executive_summary = parsed.get("executive_summary", "")

        # Sort by priority: critical > high > medium > low
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        insights.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 4))

        return {
            "success": True,
            "executive_summary": executive_summary,
            "insights": insights,
            "signals_used": {
                "forecasts": forecast_signals.get("available", False),
                "anomalies": anomaly_signals.get("available", False),
                "sales_data": sales_signals.get("available", False),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "insight_count": len(insights),
        }

    except json.JSONDecodeError as e:
        logger.error(f"Insight synthesis JSON parse error: {e}")
        return {
            "success": False,
            "error": "Failed to parse AI response. Please try again.",
            "insights": [],
            "executive_summary": "",
        }
    except Exception as e:
        logger.error(f"Insight synthesis failed: {e}")
        return {
            "success": False,
            "error": f"Insight generation failed: {str(e)}",
            "insights": [],
            "executive_summary": "",
        }
