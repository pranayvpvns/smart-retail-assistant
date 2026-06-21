from flask import Blueprint, request, jsonify, g
from pydantic import ValidationError

from app.models.schemas import RegisterRequest, UserRegisterRequest, LoginRequest
from app.models.db_models import create_user_document
from app.utils.auth_helpers import (
    hash_password,
    verify_password,
    generate_store_id,
    generate_user_id,
    create_access_token,
)
from app.db.mongo import get_database

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


# ─────────────────────────────────────────────────────────────
# OWNER Registration (existing endpoint — unchanged contract)
# ─────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
def register():
    """
    POST /api/v1/auth/register
    Body: { "email": "", "password": "", "store_name": "" }
    Creates an OWNER account.
    """
    try:
        body = RegisterRequest(**request.get_json(force=True))
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 422
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    db = get_database()

    existing = db["users"].find_one({"email": body.email})
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    hashed   = hash_password(body.password)
    store_id = generate_store_id()

    user_doc = create_user_document(
        email=body.email,
        hashed_password=hashed,
        store_name=body.store_name,
        store_id=store_id,
        role="owner",
    )
    db["users"].insert_one(user_doc)

    token = create_access_token({
        "email":      body.email,
        "role":       "owner",
        "store_id":   store_id,
        "store_name": body.store_name,
        "user_id":    "",
        "name":       body.store_name,
    })

    return jsonify({
        "access_token": token,
        "token_type":   "bearer",
        "role":         "owner",
        "store_id":     store_id,
        "store_name":   body.store_name,
        "email":        body.email,
    }), 201


# ─────────────────────────────────────────────────────────────
# USER Registration (new — for marketplace buyers)
# ─────────────────────────────────────────────────────────────

@auth_bp.route("/user/register", methods=["POST"])
def user_register():
    """
    POST /api/v1/auth/user/register
    Body: { "email": "", "password": "", "name": "" }
    Creates a USER (buyer) account.
    """
    try:
        body = UserRegisterRequest(**request.get_json(force=True))
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 422
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    db = get_database()

    existing = db["users"].find_one({"email": body.email})
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    hashed  = hash_password(body.password)
    user_id = generate_user_id()

    user_doc = create_user_document(
        email=body.email,
        hashed_password=hashed,
        store_name="",
        store_id="",
        role="user",
        name=body.name,
    )
    db["users"].insert_one(user_doc)

    token = create_access_token({
        "email":      body.email,
        "role":       "user",
        "user_id":    user_id,
        "name":       body.name,
        "store_id":   "",
        "store_name": "",
    })

    return jsonify({
        "access_token": token,
        "token_type":   "bearer",
        "role":         "user",
        "user_id":      user_id,
        "name":         body.name,
        "email":        body.email,
    }), 201


# ─────────────────────────────────────────────────────────────
# Shared Login (both owners and users)
# ─────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /api/v1/auth/login
    Body: { "email": "", "password": "" }
    Works for both owners and users. Returns role in response.
    """
    try:
        body = LoginRequest(**request.get_json(force=True))
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 422
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    db   = get_database()
    user = db["users"].find_one({"email": body.email})

    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    if not verify_password(body.password, user["password"]):
        return jsonify({"error": "Invalid email or password"}), 401

    if not user.get("is_active", True):
        return jsonify({"error": "Account is disabled. Contact support."}), 403

    role = user.get("role", "owner")

    # Build JWT payload based on role
    payload = {
        "email":      user["email"],
        "role":       role,
        "store_id":   user.get("store_id", ""),
        "store_name": user.get("store_name", ""),
        "user_id":    user.get("user_id", ""),
        "name":       user.get("name", user.get("store_name", "")),
    }
    token = create_access_token(payload)

    response = {
        "access_token": token,
        "token_type":   "bearer",
        "role":         role,
        "email":        user["email"],
        "store_id":     user.get("store_id", ""),
        "store_name":   user.get("store_name", ""),
        "user_id":      user.get("user_id", ""),
        "name":         user.get("name", user.get("store_name", "")),
    }
    return jsonify(response), 200


# ─────────────────────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
def logout():
    """
    POST /api/v1/auth/logout
    JWT is stateless — client simply discards the token.
    """
    return jsonify({"message": "Logged out successfully"}), 200


# ─────────────────────────────────────────────────────────────
# Whoami  (convenient for frontend to verify token + get role)
# ─────────────────────────────────────────────────────────────

@auth_bp.route("/me", methods=["GET"])
def whoami():
    """
    GET /api/v1/auth/me
    Returns basic profile from JWT without hitting the DB.
    """
    from app.utils.auth_helpers import decode_access_token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing token"}), 401
    try:
        payload = decode_access_token(auth_header.split(" ", 1)[1])
        return jsonify({
            "email":      payload.get("email"),
            "role":       payload.get("role", "owner"),
            "store_id":   payload.get("store_id", ""),
            "store_name": payload.get("store_name", ""),
            "user_id":    payload.get("user_id", ""),
            "name":       payload.get("name", ""),
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 401