import jwt
import bcrypt
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, g
from app.config import get_settings

settings = get_settings()


# ── Password Helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hashes a plain text password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Returns True if plain matches the stored bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── ID Generators ─────────────────────────────────────────────────────────────

def generate_store_id() -> str:
    """Generates a unique store ID for a new owner."""
    return f"S-{uuid.uuid4().hex[:12].upper()}"


def generate_user_id() -> str:
    """Generates a unique user ID for a buyer account."""
    return f"U-{uuid.uuid4().hex[:12].upper()}"


# ── Token Helpers ─────────────────────────────────────────────────────────────

def create_access_token(payload: dict) -> str:
    """
    Creates a signed JWT token.
    Payload should include at minimum: email, role.
    Owners also carry: store_id, store_name.
    Buyers carry: user_id, name.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )
    to_encode = payload.copy()
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """
    Decodes and validates a JWT token.
    Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError on failure.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


# ── Route Protection Decorator ────────────────────────────────────────────────

def token_required(f):
    """
    Decorator for routes that require ANY valid JWT (owner or user).
    Attaches full user info to flask.g.current_user:
      - email, role
      - store_id, store_name  (owners only; empty string for buyers)
      - user_id, name         (buyers only; empty string for owners)
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or malformed Authorization header"}), 401

        token = auth_header.split(" ", 1)[1]

        try:
            payload = decode_access_token(token)
            g.current_user = {
                "email":      payload.get("email", ""),
                "role":       payload.get("role", "owner"),
                # Owner fields
                "store_id":   payload.get("store_id", ""),
                "store_name": payload.get("store_name", ""),
                # User/buyer fields
                "user_id":    payload.get("user_id", ""),
                "name":       payload.get("name", ""),
            }
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired. Please log in again."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token."}), 401

        return f(*args, **kwargs)
    return decorated


def role_required(*allowed_roles):
    """
    Decorator factory that restricts a route to specific roles.
    Must be used AFTER @token_required.

    Usage:
        @app.route("/owner/only")
        @token_required
        @role_required("owner")
        def owner_only_view(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = getattr(g, "current_user", {}).get("role", "")
            if user_role not in allowed_roles:
                return jsonify({
                    "error": f"Access denied. Required role(s): {', '.join(allowed_roles)}."
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator