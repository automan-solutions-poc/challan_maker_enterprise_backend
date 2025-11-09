# routes/admin/tenant_users.py
from flask import Blueprint, request, jsonify
from utils.db import get_db_connection
from utils.auth import admin_token_required, hash_password
from datetime import datetime
import json

tenant_users_bp = Blueprint("tenant_users", __name__)

# --------------------------------------------------------------------
# 🔹 List All Users for a Tenant
# --------------------------------------------------------------------
@tenant_users_bp.route("/<int:tenant_id>", methods=["GET"])
@admin_token_required
def list_users(tenant_id):
    """Fetch all users for a specific tenant"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, tenant_id, name, email, role, created_at, is_active
            FROM users
            WHERE tenant_id=%s
            ORDER BY created_at DESC
        """, (tenant_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        users = [
            {
                "id": r[0],
                "tenant_id": r[1],
                "name": r[2],
                "email": r[3],
                "role": r[4],
                "created_at": r[5].strftime("%Y-%m-%d %H:%M:%S"),
                "is_active": r[6],
            }
            for r in rows
        ]

        return jsonify({"users": users}), 200

    except Exception as e:
        print("❌ Error listing users:", e)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to fetch users"}), 500
    finally:
        if conn:
            conn.close()


# --------------------------------------------------------------------
# 🔹 Create a New Tenant User (bcrypt password)
# --------------------------------------------------------------------
@tenant_users_bp.route("/<int:tenant_id>", methods=["POST"])
@admin_token_required
def create_user(tenant_id):
    """Create a new tenant user"""
    conn = None
    try:
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        password = body.get("password")
        role = body.get("role", "staff")

        if not name or not email or not password:
            return jsonify({"error": "name, email, and password are required"}), 400

        # ✅ Hash password securely (bcrypt)
        hashed = hash_password(password)

        conn = get_db_connection()
        cur = conn.cursor()

        # Check for existing user
        cur.execute("SELECT id FROM users WHERE tenant_id=%s AND email=%s", (tenant_id, email))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"error": "User with this email already exists for tenant"}), 400

        # Insert user
        cur.execute("""
            INSERT INTO users (tenant_id, name, email, password_hash, role, created_at, is_active)
            VALUES (%s, %s, %s, %s, %s, NOW(), TRUE)
            RETURNING id, tenant_id, name, email, role, created_at, is_active
        """, (tenant_id, name, email, hashed, role))
        new_user = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        user_dict = {
            "id": new_user[0],
            "tenant_id": new_user[1],
            "name": new_user[2],
            "email": new_user[3],
            "role": new_user[4],
            "created_at": new_user[5].strftime("%Y-%m-%d %H:%M:%S"),
            "is_active": new_user[6],
        }

        return jsonify({
            "message": "✅ Tenant user created successfully",
            "user": user_dict
        }), 201

    except Exception as e:
        print("❌ Error creating tenant user:", e)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to create tenant user"}), 500
    finally:
        if conn:
            conn.close()


# --------------------------------------------------------------------
# 🔹 Update Tenant User
# --------------------------------------------------------------------
@tenant_users_bp.route("/<int:tenant_id>/<int:user_id>", methods=["PUT"])
@admin_token_required
def update_user(tenant_id, user_id):
    """Update an existing tenant user"""
    conn = None
    try:
        body = request.get_json(silent=True) or {}
        name = body.get("name")
        role = body.get("role")
        is_active = body.get("is_active")

        conn = get_db_connection()
        cur = conn.cursor()

        updates, params = [], []
        if name is not None:
            updates.append("name=%s")
            params.append(name)
        if role is not None:
            updates.append("role=%s")
            params.append(role)
        if is_active is not None:
            updates.append("is_active=%s")
            params.append(bool(is_active))

        if not updates:
            return jsonify({"message": "No fields to update"}), 200

        params.extend([tenant_id, user_id])
        query = f"""
            UPDATE users
            SET {', '.join(updates)}, updated_at=NOW()
            WHERE tenant_id=%s AND id=%s
            RETURNING id, tenant_id, name, email, role, created_at, is_active
        """
        cur.execute(query, tuple(params))
        updated = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if not updated:
            return jsonify({"error": "User not found"}), 404

        user_dict = {
            "id": updated[0],
            "tenant_id": updated[1],
            "name": updated[2],
            "email": updated[3],
            "role": updated[4],
            "created_at": updated[5].strftime("%Y-%m-%d %H:%M:%S"),
            "is_active": updated[6],
        }

        return jsonify({"message": "✅ User updated successfully", "user": user_dict}), 200

    except Exception as e:
        print("❌ Error updating tenant user:", e)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to update tenant user"}), 500
    finally:
        if conn:
            conn.close()


# --------------------------------------------------------------------
# 🔹 Delete Tenant User
# --------------------------------------------------------------------
@tenant_users_bp.route("/<int:tenant_id>/<int:user_id>", methods=["DELETE"])
@admin_token_required
def delete_user(tenant_id, user_id):
    """Delete a tenant user"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE tenant_id=%s AND id=%s RETURNING id", (tenant_id, user_id))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if not deleted:
            return jsonify({"error": "User not found"}), 404

        return jsonify({"message": "🗑️ User deleted successfully"}), 200

    except Exception as e:
        print("❌ Error deleting tenant user:", e)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to delete tenant user"}), 500
    finally:
        if conn:
            conn.close()

# --------------------------------------------
# 🔹 Get Tenant User Summary (for dashboard)
# --------------------------------------------
@tenant_users_bp.route("/summary", methods=["GET", "OPTIONS"])
@admin_token_required
def tenant_user_summary():
    """Returns a summary of all tenant users (for admin dashboard)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
        total_users = cur.fetchone()[0]
        cur.close()
        conn.close()

        return jsonify({"total_users": total_users}), 200

    except Exception as e:
        print("❌ Error in tenant_user_summary:", e)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to fetch tenant user summary"}), 500
