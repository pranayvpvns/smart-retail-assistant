"""
routes/products.py  (rewrite)
─────────────────────────────
Owner CRUD:
  POST   /api/v1/products           — add product
  PUT    /api/v1/products/<id>      — update product
  DELETE /api/v1/products/<id>      — delete product
  GET    /api/v1/products/mine      — owner's own listings

Marketplace (any authenticated user):
  GET    /api/v1/products           — browse (search + category + page)
  GET    /api/v1/products/categories
  GET    /api/v1/products/<id>      — product detail
"""
from flask import Blueprint, request, jsonify, g, Response
from app.utils.auth_helpers import token_required, role_required
from app.services.product_catalog_service import (
    add_product,
    update_product,
    delete_product,
    get_owner_products,
    get_marketplace_products,
    get_product_detail,
    get_categories,
    import_products_from_csv,
    generate_products_csv_template,
)
from app.db.mongo import get_database

products_bp = Blueprint("products", __name__, url_prefix="/api/v1/products")


# ─── Owner: Add Product ────────────────────────────────────────
@products_bp.route("", methods=["POST"])
@token_required
@role_required("owner")
def create_product():
    body     = request.get_json(force=True) or {}
    db       = get_database()
    user     = g.current_user
    result   = add_product(
        owner_id=user["store_id"],
        store_name=user.get("store_name", ""),
        data=body,
        db=db,
    )
    return jsonify(result), 201 if result["success"] else 400


# ─── Marketplace: Browse ───────────────────────────────────────
@products_bp.route("", methods=["GET"])
@token_required
def list_products():
    search   = request.args.get("search",   "").strip()
    category = request.args.get("category", "").strip()
    page     = max(1, int(request.args.get("page",  1)))
    limit    = min(50, max(1, int(request.args.get("limit", 20))))
    db       = get_database()
    result   = get_marketplace_products(db=db, search=search, category=category, page=page, limit=limit)
    return jsonify(result), 200


# ─── Owner: Own Listings ───────────────────────────────────────
@products_bp.route("/mine", methods=["GET"])
@token_required
@role_required("owner")
def owner_products():
    db    = get_database()
    items = get_owner_products(g.current_user["store_id"], db)
    return jsonify({"products": items, "count": len(items)}), 200


# ─── Categories ────────────────────────────────────────────────
@products_bp.route("/categories", methods=["GET"])
@token_required
def list_categories():
    db   = get_database()
    cats = get_categories(db)
    return jsonify({"categories": cats}), 200


# ─── Product Detail ────────────────────────────────────────────
@products_bp.route("/<product_id>", methods=["GET"])
@token_required
def product_detail(product_id: str):
    db     = get_database()
    detail = get_product_detail(product_id, db)
    if not detail:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(detail), 200


# ─── Owner: Update Product ─────────────────────────────────────
@products_bp.route("/<product_id>", methods=["PUT"])
@token_required
@role_required("owner")
def edit_product(product_id: str):
    body   = request.get_json(force=True) or {}
    db     = get_database()
    result = update_product(
        product_id=product_id,
        owner_id=g.current_user["store_id"],
        updates=body,
        db=db,
    )
    return jsonify(result), 200 if result["success"] else 404


# ─── Owner: Delete Product ─────────────────────────────────────
@products_bp.route("/<product_id>", methods=["DELETE"])
@token_required
@role_required("owner")
def remove_product(product_id: str):
    db     = get_database()
    result = delete_product(
        product_id=product_id,
        owner_id=g.current_user["store_id"],
        db=db,
    )
    return jsonify(result), 200 if result["success"] else 404


# ─── Owner: Bulk Import from CSV ───────────────────────────────
@products_bp.route("/import-csv", methods=["POST"])
@token_required
@role_required("owner")
def import_csv():
    """
    POST /api/v1/products/import-csv
    multipart/form-data:
      file   — CSV file
      mode   — "upsert" (default) | "insert_new"
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return jsonify({"success": False, "error": "Only .csv files are accepted"}), 400

    mode = request.form.get("mode", "upsert")
    user = g.current_user
    db   = get_database()

    result = import_products_from_csv(
        owner_id=user["store_id"],
        store_name=user.get("store_name", ""),
        file_obj=file,
        db=db,
        mode=mode,
    )
    status = 200 if result.get("success") else 400
    return jsonify(result), status


# ─── CSV Template Download ─────────────────────────────────────
@products_bp.route("/template", methods=["GET"])
@token_required
@role_required("owner")
def download_template():
    """GET /api/v1/products/template — returns a starter CSV for import."""
    csv_content = generate_products_csv_template()
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=products_template.csv"},
    )
