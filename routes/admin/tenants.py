from flask import Blueprint, request, jsonify
from utils.db import get_db_connection
from werkzeug.utils import secure_filename
import os, json, psycopg2.extras
from datetime import datetime

tenants_bp = Blueprint("tenants", __name__)

UPLOAD_FOLDER = os.path.join("static", "tenant_logos")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------
# 🔹 Helper: Convert JSON safely
# ---------------------------------------------------------------------
def safe_json(v):
    if not v:
        return {}
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {}


# ---------------------------------------------------------------------
# 📋 Get All Tenants
# ---------------------------------------------------------------------
@tenants_bp.route("/tenants", methods=["GET"])
def get_all_tenants():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT id, name, email, logo_url, theme_color, plan, subscription_start,
                   subscription_end, status, created_at
            FROM tenants
            ORDER BY created_at DESC
        """)
        tenants = cur.fetchall()

        cur.close()
        conn.close()
        return jsonify({"tenants": tenants}), 200

    except Exception as e:
        print("❌ Error fetching tenants:", e)
        if conn and not conn.closed:
            conn.rollback()
        return jsonify({"error": "Failed to fetch tenants"}), 500
    finally:
        if conn and not conn.closed:
            conn.close()


# ---------------------------------------------------------------------
# 🆕 Create New Tenant
# ---------------------------------------------------------------------
@tenants_bp.route("/tenants", methods=["POST"])
def create_tenant():
    conn = None
    try:
        # ✅ Handle form-data (supports logo upload)
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            data = json.loads(request.form.get("data", "{}"))
            logo_file = request.files.get("logo")
        else:
            data = request.get_json() or {}
            logo_file = None

        name = data.get("name")
        email = data.get("email")
        theme_color = data.get("theme_color", "#114e9e")
        plan = data.get("plan", "Free")
        subscription_start = data.get("subscription_start", datetime.utcnow().strftime("%Y-%m-%d"))
        subscription_end = data.get("subscription_end", None)

        if not name or not email:
            return jsonify({"error": "Tenant name and email are required"}), 400

        # ✅ Handle logo upload
        logo_url = None
        if logo_file:
            filename = secure_filename(logo_file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            logo_file.save(filepath)
            logo_url = f"/static/tenant_logos/{filename}"

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ✅ Check duplicate
        cur.execute("SELECT id FROM tenants WHERE email=%s", (email,))
        if cur.fetchone():
            return jsonify({"error": "A tenant with this email already exists"}), 409

        # ✅ Insert tenant
        cur.execute("""
            INSERT INTO tenants (name, email, logo_url, theme_color, plan, subscription_start, subscription_end, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', NOW())
            RETURNING id, name, email, logo_url, theme_color, plan, subscription_start, subscription_end, status, created_at
        """, (name, email, logo_url, theme_color, plan, subscription_start, subscription_end))

        new_tenant = cur.fetchone()
        conn.commit()

        cur.close()
        conn.close()
        return jsonify({
            "message": "✅ Tenant created successfully",
            "tenant": new_tenant
        }), 201

    except Exception as e:
        print("❌ Error creating tenant:", e)
        if conn and not conn.closed:
            conn.rollback()
        return jsonify({"error": "Failed to create tenant"}), 500
    finally:
        if conn and not conn.closed:
            conn.close()


# ---------------------------------------------------------------------
# 🧾 Get Tenant by ID
# ---------------------------------------------------------------------
@tenants_bp.route("/tenants/<int:tenant_id>", methods=["GET"])
def get_tenant(tenant_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT * FROM tenants WHERE id=%s", (tenant_id,))
        tenant = cur.fetchone()

        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404

        cur.close()
        conn.close()
        return jsonify({"tenant": tenant}), 200

    except Exception as e:
        print("❌ Error fetching tenant:", e)
        if conn and not conn.closed:
            conn.rollback()
        return jsonify({"error": "Failed to fetch tenant"}), 500
    finally:
        if conn and not conn.closed:
            conn.close()


# ---------------------------------------------------------------------
# ✏️ Update Tenant
# ---------------------------------------------------------------------
@tenants_bp.route("/tenants/<int:tenant_id>", methods=["PUT"])
def update_tenant(tenant_id):
    conn = None
    try:
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            data = json.loads(request.form.get("data", "{}"))
            logo_file = request.files.get("logo")
        else:
            data = request.get_json() or {}
            logo_file = None

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ✅ Fetch current tenant
        cur.execute("SELECT logo_url FROM tenants WHERE id=%s", (tenant_id,))
        current = cur.fetchone()
        if not current:
            return jsonify({"error": "Tenant not found"}), 404

        logo_url = current["logo_url"]
        if logo_file:
            filename = secure_filename(logo_file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            logo_file.save(filepath)
            logo_url = f"/static/tenant_logos/{filename}"

        # ✅ Update details
        cur.execute("""
            UPDATE tenants
            SET name=%s, email=%s, theme_color=%s, plan=%s,
                subscription_start=%s, subscription_end=%s, logo_url=%s, status=%s
            WHERE id=%s
            RETURNING id, name, email, logo_url, theme_color, plan, subscription_start, subscription_end, status
        """, (
            data.get("name"),
            data.get("email"),
            data.get("theme_color"),
            data.get("plan"),
            data.get("subscription_start"),
            data.get("subscription_end"),
            logo_url,
            data.get("status", "active"),
            tenant_id,
        ))

        updated_tenant = cur.fetchone()
        conn.commit()

        cur.close()
        conn.close()
        return jsonify({
            "message": "✅ Tenant updated successfully",
            "tenant": updated_tenant
        }), 200

    except Exception as e:
        print("❌ Error updating tenant:", e)
        if conn and not conn.closed:
            conn.rollback()
        return jsonify({"error": "Failed to update tenant"}), 500
    finally:
        if conn and not conn.closed:
            conn.close()


# ---------------------------------------------------------------------
# 🗑️ Delete Tenant
# ---------------------------------------------------------------------
@tenants_bp.route("/tenants/<int:tenant_id>", methods=["DELETE"])
def delete_tenant(tenant_id):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("DELETE FROM tenants WHERE id=%s", (tenant_id,))
        conn.commit()

        cur.close()
        conn.close()
        return jsonify({"message": "🗑️ Tenant deleted successfully"}), 200

    except Exception as e:
        print("❌ Error deleting tenant:", e)
        if conn and not conn.closed:
            conn.rollback()
        return jsonify({"error": "Failed to delete tenant"}), 500
    finally:
        if conn and not conn.closed:
            conn.close()
