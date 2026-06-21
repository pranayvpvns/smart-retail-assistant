import re
import uuid
from flask import Blueprint, request, jsonify, g
from app.utils.auth_helpers import token_required
from app.services.agent_service import run_agent
from app.services.chat_service import save_message, get_history, list_sessions, delete_session
from app.services.rag_service import embed_sales_records
from app.db.mongo import get_database

chat_bp = Blueprint("chat", __name__, url_prefix="/api/v1/chat")


@chat_bp.route("", methods=["POST"])
@token_required
def chat():
    """
    POST /api/v1/chat
    Body: { "message": "...", "session_id": "optional-uuid" }
    Auth: Bearer token required

    For buyers, intercepts [PLACE_ORDER: product_id, quantity] action tags
    from the marketplace agent and executes the real order placement.
    """
    body = request.get_json(force=True) or {}
    message = body.get("message", "").strip()

    if not message:
        return jsonify({"error": "message cannot be empty"}), 400

    session_id = body.get("session_id") or str(uuid.uuid4())

    role = g.current_user["role"]
    context_id = (
        g.current_user["store_id"]
        if role == "owner"
        else (g.current_user.get("user_id") or g.current_user.get("email", ""))
    )
    db = get_database()

    # Save user message
    save_message(
        session_id=session_id,
        store_id=context_id,
        role="user",
        content=message,
        db=db,
    )

    # Run through the agent orchestrator
    result = run_agent(query=message, store_id=context_id, db=db, role=role)
    response_text = result["response"]
    order_placed = None

    # ── Intercept [PLACE_ORDER] action from marketplace agent ────────────
    if role == "user":
        place_match = re.search(r"\[PLACE_ORDER:\s*([A-Za-z0-9\-]+),\s*(\d+)\]", response_text)
        if place_match:
            product_id = place_match.group(1).strip()
            quantity = int(place_match.group(2).strip())

            try:
                from app.services.order_flow_service import place_order
                user_id = g.current_user.get("user_id") or g.current_user.get("email", "")
                order_result = place_order(
                    user_id=user_id,
                    user_email=g.current_user.get("email", ""),
                    product_id=product_id,
                    quantity=quantity,
                    db=db,
                )
                if order_result.get("success"):
                    order_placed = {
                        "success": True,
                        "order_id": order_result.get("order_id"),
                        "product_id": product_id,
                        "quantity": quantity,
                    }
                    # Remove the action tag from the display text
                    response_text = re.sub(r"\[PLACE_ORDER:[^\]]+\]", "", response_text).strip()
                    response_text = (
                        f"✅ **Order Placed!** Your order has been confirmed.\n"
                        f"📦 Order ID: `{order_result.get('order_id')}`\n\n"
                        + response_text
                    )
                else:
                    # Order failed — replace tag with error message
                    error_msg = order_result.get("error", "Order could not be placed.")
                    response_text = re.sub(r"\[PLACE_ORDER:[^\]]+\]", "", response_text).strip()
                    response_text = f"❌ {error_msg}\n\n" + response_text

            except Exception as e:
                response_text = re.sub(r"\[PLACE_ORDER:[^\]]+\]", "", response_text).strip()
                response_text = f"❌ Order failed: {str(e)}\n\n" + response_text

    # Save assistant response
    save_message(
        session_id=session_id,
        store_id=context_id,
        role="assistant",
        content=response_text,
        db=db,
        metadata={
            "intent": result["intent"],
            "agents_used": result["agents_used"],
            "order_placed": order_placed,
        },
    )

    response_payload = {
        "session_id": session_id,
        "response": response_text,
        "intent": result["intent"],
        "agents_used": result["agents_used"],
    }

    if order_placed:
        response_payload["order_placed"] = order_placed

    return jsonify(response_payload), 200


@chat_bp.route("/history/<session_id>", methods=["GET"])
@token_required
def history(session_id: str):
    """GET /api/v1/chat/history/<session_id>"""
    db = get_database()
    role = g.current_user["role"]
    context_id = (
        g.current_user["store_id"]
        if role == "owner"
        else (g.current_user.get("user_id") or g.current_user.get("email"))
    )
    messages = get_history(session_id=session_id, store_id=context_id, db=db)
    return jsonify({"session_id": session_id, "messages": messages}), 200


@chat_bp.route("/sessions", methods=["GET"])
@token_required
def sessions():
    """GET /api/v1/chat/sessions"""
    db = get_database()
    role = g.current_user["role"]
    context_id = (
        g.current_user["store_id"]
        if role == "owner"
        else (g.current_user.get("user_id") or g.current_user.get("email"))
    )
    result = list_sessions(store_id=context_id, db=db)
    return jsonify({"sessions": result}), 200


@chat_bp.route("/sessions/<session_id>", methods=["DELETE"])
@token_required
def delete_session_route(session_id: str):
    """DELETE /api/v1/chat/sessions/<session_id>"""
    db = get_database()
    role = g.current_user["role"]
    context_id = (
        g.current_user["store_id"]
        if role == "owner"
        else (g.current_user.get("user_id") or g.current_user.get("email"))
    )
    deleted = delete_session(session_id=session_id, store_id=context_id, db=db)
    return jsonify({"deleted": deleted, "session_id": session_id}), 200


@chat_bp.route("/embed", methods=["POST"])
@token_required
def embed():
    """POST /api/v1/chat/embed — embeds sales records into vector store"""
    db = get_database()
    store_id = g.current_user["store_id"]
    result = embed_sales_records(store_id=store_id, db=db)

    if not result["success"]:
        return jsonify(result), 400

    return jsonify({
        "success": True,
        "message": f"Embedded {result['records_embedded']} records into vector store",
    }), 200