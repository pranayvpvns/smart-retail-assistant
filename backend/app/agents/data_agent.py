import os
import sys
import pandas as pd
import re
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
)
from app.config import get_settings
from app.services.rag_service import similarity_search
from app.services.product_catalog_service import add_product, update_product, get_owner_products
from pymongo.database import Database

settings = get_settings()

def get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.2,
        max_tokens=800,
    )

# ── Inventory Tools ──────────────────────────────────────────────────────────

def _get_inventory_summary(store_id: str, db: Database) -> str:
    """Fetches real-time inventory from the 'products' collection."""
    products = get_owner_products(store_id, db)
    if not products:
        return "Your inventory is currently empty."
    
    lines = [f"- {p['product_name']} (ID: {p['product_id']}): {p['stock']} in stock | Price: ₹{p['price']}" for p in products]
    return "Current Inventory:\n" + "\n".join(lines)

def _get_low_stock_report(store_id: str, db: Database, threshold: int = 20) -> str:
    """Identifies products below a certain stock threshold."""
    products = get_owner_products(store_id, db)
    low = [p for p in products if int(p.get("stock", 0)) < threshold]
    if not low:
        return f"All items are well-stocked (above {threshold})."
    
    lines = [f"- {p['product_name']}: {p['stock']} left" for p in low]
    return f"Low Stock Alert (<{threshold}):\n" + "\n".join(lines)

def _update_product_stock(store_id: str, product_name: str, change: int, db: Database) -> str:
    """Increases or decreases stock for a product by name."""
    products = get_owner_products(store_id, db)
    # Case-insensitive match
    p = next((p for p in products if p["product_name"].lower() == product_name.lower()), None)
    if not p:
        return f"Could not find product '{product_name}' in your inventory."
    
    new_stock = max(0, int(p.get("stock", 0)) + change)
    res = update_product(p["product_id"], store_id, {"stock": new_stock}, db)
    if res["success"]:
        return f"Success! '{product_name}' stock updated to {new_stock}."
    return f"Error updating stock: {res.get('error')}"

def _add_new_product(store_id: str, store_name: str, name: str, price: float, stock: int, category: str, db: Database) -> str:
    """Adds a new product to the inventory."""
    res = add_product(store_id, store_name, {
        "product_name": name,
        "price": price,
        "stock": stock,
        "category": category,
        "description": "Added via AI Assistant"
    }, db)
    if res["success"]:
        return f"Success! Added '{name}' to inventory with {stock} units at ₹{price}."
    return f"Error adding product: {res.get('error')}"

# ── Main Stats Logic ─────────────────────────────────────────────────────────

def _get_summary_stats(store_id: str, db: Database) -> str:
    """
    Pulls aggregate stats from sales_records for financial overview.
    """
    records = list(db["sales_records"].find({"store_id": store_id}, {"_id": 0}))
    if not records:
        sales_str = "No sales records available for analytics."
    else:
        df = pd.DataFrame(records)
        df["quantity_sold"] = pd.to_numeric(df["quantity_sold"], errors="coerce")
        df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
        total_revenue = df["revenue"].sum()
        total_units = df["quantity_sold"].sum()
        date_range = f"{df['date'].min()} to {df['date'].max()}"
        sales_str = f"Analytics Summary: ₹{total_revenue:,.2f} revenue, {int(total_units)} units sold ({date_range})."

    # Get real-time inventory from products collection
    inventory_str = _get_low_stock_report(store_id, db)

    return f"{sales_str}\n\nInventory Status:\n{inventory_str}"

# ── Orchestrator ─────────────────────────────────────────────────────────────

def run_data_agent(query: str, store_id: str, db: Database) -> str:
    """
    Data Agent — Handles analytics questions AND Inventory Management.
    """
    llm = get_llm()
    
    # Ground truth from MongoDB
    stats = _get_summary_stats(store_id, db)
    inventory_detail = _get_inventory_summary(store_id, db)

    # Relevant chunks from ChromaDB
    chunks = similarity_search(store_id, query, k=6)
    context = "\n".join(chunks) if chunks else "No relevant records found."

    system_prompt = f"""You are an Inventory & Data Manager for a retail store.
Your job is to answer questions about sales AND manage the inventory.

CONTEXT:
1. Sales Analytics: {stats}
2. Detailed Inventory: {inventory_detail}

INVENTORY ACTIONS:
If the user wants to ADD a product or UPDATE stock, you MUST respond with a special ACTION command at the START of your message in square brackets.
Commands:
- [ADD_PRODUCT: name, price, stock, category] (Price must be a number, stock must be an integer)
- [UPDATE_STOCK: name, change_amount] (Use a positive integer like 10 to increase, or a negative integer like -5 to decrease)

Example User: "Add 20 to the stock of milk"
Example Response: "[UPDATE_STOCK: milk, 20] I've successfully added 20 units to the milk inventory. New stock level confirmed."

Example User: "Register a new item called Headset for 1500 rupees with 10 items in Electronics"
Example Response: "[ADD_PRODUCT: Headset, 1500, 10, Electronics] I've registered the new 'Headset' in the Electronics category at ₹1,500.00."

RULES:
- Always use ₹ for currency.
- If you perform an action, clearly state what you did in the natural language part.
- If you aren't sure about the name of the product, check the 'Detailed Inventory' list provided below.
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query),
    ]

    try:
        response_obj = llm.invoke(messages)
        response = response_obj.content.strip()
    except Exception as e:
        return f"Error calling AI: {e}"
    
    # ── Parse and Execute Actions ─────────────────────────────────────────────
    
    # [ADD_PRODUCT: name, price, stock, category]
    add_match = re.search(r"\[ADD_PRODUCT:\s*(.*?),\s*(.*?),\s*(.*?),\s*(.*?)\]", response)
    if add_match:
        try:
            name, price, stock, cat = add_match.groups()
            user_doc = db["users"].find_one({"store_id": store_id})
            store_name = user_doc.get("store_name", "My Store") if user_doc else "My Store"
            action_res = _add_new_product(store_id, store_name, name, float(price), int(stock), cat, db)
            response = response.replace(add_match.group(0), "").strip()
            return f"{response}\n\n✨ {action_res}"
        except Exception as e: 
            return f"{response}\n\n⚠️ Failed to add product: {e}"

    # [UPDATE_STOCK: name, change_amount]
    update_match = re.search(r"\[UPDATE_STOCK:\s*(.*?),\s*(.*?)\]", response)
    if update_match:
        try:
            name, change = update_match.groups()
            action_res = _update_product_stock(store_id, name, int(change), db)
            response = response.replace(update_match.group(0), "").strip()
            return f"{response}\n\n✨ {action_res}"
        except Exception as e:
            return f"{response}\n\n⚠️ Failed to update stock: {e}"

    return response