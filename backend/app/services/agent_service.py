import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

PROJECT_ROOT = os.path.abspath(
    os.path.join(CURRENT_DIR, "..", "..", "..")
)

BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
)
from app.config import get_settings
from app.agents.data_agent import run_data_agent
from app.agents.ml_agent import run_ml_agent
from app.agents.advisor_agent import run_advisor_agent
from app.agents.marketplace_agent import run_marketplace_agent
from pymongo.database import Database

settings = get_settings()


# ── Intent Classification ─────────────────────────────────────────────────────

INTENT_DATA     = "data"       # questions about past sales, revenue, stock
INTENT_ML       = "ml"         # questions about forecasts, anomalies
INTENT_COMBINED = "combined"   # business advice needing both
INTENT_UNKNOWN  = "unknown"    # off-topic or unclear

def classify_intent(query: str) -> str:
    """
    Uses a lightweight LLM call to classify the user's intent.
    Returns one of: data | ml | combined | unknown
    """
    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0,
        max_tokens=10,
    )

    system_prompt = """Classify the user's retail question into exactly one category.
Reply with ONLY the category word, nothing else.

Categories:
- data      : questions about sales, revenue, stock levels, AND commands to manage inventory (add products, update stock)
- ml        : questions about forecasts, predictions, anomalies, unusual patterns
- combined  : questions asking for business advice, restocking decisions, what to do next
- unknown   : completely unrelated to retail
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Question: {query}"),
    ]

    try:
        # Keyword-based override for inventory commands to ensure reliability
        keywords = ["register", "add product", "update stock", "increase stock", "decrease stock", "new product"]
        if any(kw in query.lower() for kw in keywords):
            return INTENT_DATA

        response = llm.invoke(messages)
        intent = response.content.strip().lower()
        if intent not in (INTENT_DATA, INTENT_ML, INTENT_COMBINED, INTENT_UNKNOWN):
            return INTENT_COMBINED   # default to combined if ambiguous
        return intent
    except Exception:
        return INTENT_COMBINED


# ── Main Orchestrator ─────────────────────────────────────────────────────────

def run_agent(query: str, store_id: str, db: Database, role: str = "owner") -> dict:
    """
    Main entry point for AI Assistant queries.
    Routes to Marketplace Agent for buyers or specialist agents for owners.
    """
    # ── BUYER ROLE (Marketplace Assistant) ──────────────────
    if role == "user":
        response = run_marketplace_agent(query, store_id, db)
        return {
            "intent": "marketplace",
            "response": response,
            "agents_used": ["marketplace_agent"],
        }

    # ── OWNER ROLE (Store Management) ───────────────────────
    intent = classify_intent(query)
    agents_used = []

    if intent == INTENT_UNKNOWN:
        return {
            "intent": intent,
            "response": (
                "I can only answer questions about your store's sales data, "
                "demand forecasts, anomalies, and inventory. "
                "Try asking: 'Which products need restocking?' or "
                "'What are the forecast sales for next week?'"
            ),
            "agents_used": [],
        }

    if intent == INTENT_DATA:
        response = run_data_agent(query, store_id, db)
        agents_used = ["data_agent"]

    elif intent == INTENT_ML:
        response = run_ml_agent(query, store_id, db)
        agents_used = ["ml_agent"]

    else:
        # Combined — run both specialist agents then synthesize
        data_insight = run_data_agent(query, store_id, db)
        ml_insight   = run_ml_agent(query, store_id, db)
        response     = run_advisor_agent(
            query=query,
            store_id=store_id,
            db=db,
            data_insight=data_insight,
            ml_insight=ml_insight,
        )
        agents_used = ["data_agent", "ml_agent", "advisor_agent"]

    return {
        "intent": intent,
        "response": response,
        "agents_used": agents_used,
    }