import os
import re
import sys
from datetime import datetime
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)
from app.config import get_settings
from pymongo.database import Database

settings = get_settings()

def get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.3,
        max_tokens=800,
    )

def _get_marketplace_context(db: Database) -> str:
    """Pulls a summary of available products from all stores."""
    products = list(db["products"].find({}, {"_id": 0}).limit(30))
    if not products:
        return "The marketplace is currently empty."

    categories = db["products"].distinct("category")
    cat_str = ", ".join(categories) if categories else "None"

    prod_list = "\n".join([
        f"- [{p.get('product_id')}] {p.get('product_name', 'Unknown')} "
        f"({p.get('category', 'General')}): ₹{p.get('price', 0)} | "
        f"Stock: {p.get('stock', 0)} | Store: {p.get('store_name', 'Unknown')}"
        for p in products
    ])

    return f"Available Categories: {cat_str}\n\nProducts:\n{prod_list}"

def _get_user_orders(user_id: str, db: Database) -> str:
    """
    Pulls order history for this specific buyer.
    Handles legacy field names (status vs order_status, created_at vs ordered_at).
    """
    # Use $or to find by user_id or user_email
    orders = list(db["ordered_sales"].find({
        "$or": [
            {"user_id": user_id},
            {"user_email": user_id}
        ]
    }, {"_id": 0}).limit(20)) # Increased limit for better context

    if not orders:
        return "You haven't placed any orders yet."

    # Sort manually in Python because the fields might be mixed (ordered_at vs created_at)
    def get_date(o):
        return o.get("ordered_at") or o.get("created_at") or datetime.min

    orders.sort(key=get_date, reverse=True)
    recent_orders = orders[:8]

    ord_list = []
    for o in recent_orders:
        oid = o.get("order_id") or "Unknown"
        name = o.get("product_name") or "Product"
        qty = o.get("quantity") or 1
        price = o.get("total_price") or o.get("total_amount") or 0
        
        # Robust status check
        raw_status = o.get("order_status") or o.get("status") or "pending"
        status = raw_status.replace("injected", "confirmed").capitalize()
        
        # Date string
        dt = get_date(o)
        date_str = dt.strftime("%Y-%m-%d") if isinstance(dt, datetime) else str(dt)[:10]
        
        ord_list.append(f"- Order {oid}: {name} x{qty} | ₹{price:,.2f} | Status: {status} | Date: {date_str}")

    return "Your Recent Orders:\n" + "\n".join(ord_list)

def run_marketplace_agent(query: str, user_id: str, db: Database) -> str:
    """
    Marketplace Shopping Assistant — helps buyers find products,
    track orders, and place new orders conversationally.
    """
    llm = get_llm()

    market_context = _get_marketplace_context(db)
    order_context = _get_user_orders(user_id, db)

    system_prompt = """You are a friendly Shopping Assistant for the Smart Retail Marketplace.

Your capabilities:
1. Help buyers find and discover products
2. Recommend products based on interests
3. Show order history and tracking status
4. Help place orders conversationally

ORDER PLACEMENT RULES:
- If the user wants to BUY something, identify the exact product from the list.
- If it exists and stock is available, respond with an ACTION TAG at the START:
  [PLACE_ORDER: <product_id>, <quantity>]
- If you place an order, tell the user it is being processed.

ORDER TRACKING RULES:
- Use the "Your Recent Orders" list to answer questions about past purchases.
- Treat "Confirmed" and "Injected" as the same thing.

GENERAL RULES:
- Use ₹ for all prices.
- Be helpful and polite.
"""

    user_prompt = f"""
{market_context}

{order_context}

Customer question: {query}
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        return f"Sorry, I encountered an error: {str(e)}."
