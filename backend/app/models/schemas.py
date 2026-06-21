from pydantic import BaseModel, field_validator
from typing import Optional


# ── Auth Schemas ────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    """Backward-compatible owner registration (keeps store_name)."""
    email: str
    password: str
    store_name: str

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, v):
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("store_name")
    @classmethod
    def store_name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError("Store name cannot be empty")
        return v.strip()


class UserRegisterRequest(BaseModel):
    """Buyer/user registration — no store required."""
    email: str
    password: str
    name: str

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, v):
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v):
        return v.lower().strip()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    store_id: str
    store_name: str
    email: str


# ── Order Schemas ────────────────────────────────────────────────────────────

class PlaceOrderRequest(BaseModel):
    """User places an order for a vendor-specific product."""
    vendor_product_id: str
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Quantity must be a positive integer")
        return v