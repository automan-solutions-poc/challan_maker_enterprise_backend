from flask import Blueprint, request, jsonify
from utils.db import get_db_connection
from utils.auth import generate_token, verify_password, tenant_token_required
import psycopg2.extras
from datetime import datetime

tenant_auth_bp = Blueprint("tenant_auth", __name__)

# ============================================================
# 🧠 TENANT USER LOGIN
# ============================================================
@tenant_auth_bp.route("/login", methods=["POST"])
def tenant_login():
    conn = None
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT 
                u.id, u.name, u.email, u.password_hash, u.role, 
                u.tenant_id, u.is_active, 
                t.name AS tenant_name
            FROM users u
            JOIN tenants t ON u.tenant_id = t.id
            WHERE u.email = %s
        """, (email,))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if not user:
            return jsonify({"error": "Invalid email or password"}), 401

        # Check if user is active
        if not user["is_active"]:
            return jsonify({"error": "Account is inactive. Contact your administrator."}), 403

        # Verify password (bcrypt)
        if not verify_password(password, user["password_hash"]):
            return jsonify({"error": "Invalid email or password"}), 401

        # ✅ Generate JWT
        token = generate_token({
            "tenant_id": user["tenant_id"],
            "user_id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "name": user["name"],
            "type": "tenant_user"
        })

        return jsonify({
            "message": "Login successful",
            "token": token,
            "user_type": "tenant_user",
            "tenant": {
                "id": user["tenant_id"],
                "name": user["tenant_name"]
            },
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"]
            }
        }), 200

    except psycopg2.Error as db_err:
        print("❌ Database error during tenant login:", db_err)
        if conn and not conn.closed:
            conn.rollback()
        return jsonify({"error": "Database connection error"}), 500
    except Exception as e:
        print("❌ Unexpected error in tenant_login:", e)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn and not conn.closed:
            conn.close()


# ============================================================
# 🚪 TENANT USER LOGOUT
# ============================================================
@tenant_auth_bp.route("/logout", methods=["POST"])
@tenant_token_required
def tenant_logout():
    """
    Log out tenant user (stateless logout).
    Frontend should simply remove the token from localStorage.
    """
    conn = None
    try:
        tenant_data = getattr(request, "tenant", None)
        if not tenant_data:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = tenant_data.get("user_id")
        tenant_id = tenant_data.get("tenant_id")

        conn = get_db_connection()
        cur = conn.cursor()

        # 🧾 Log tenant user logout event (optional)
        try:
            cur.execute("""
                INSERT INTO activity_logs (tenant_id, admin_user_id, action_type, description, timestamp)
                VALUES (%s, NULL, 'LOGOUT', %s, NOW())
            """, (tenant_id, f"Tenant user {user_id} logged out successfully"))
            conn.commit()
        except Exception as e:
            print("⚠️ Skipping activity log:", e)

        cur.close()
        conn.close()

        return jsonify({
            "message": "✅ Tenant user logged out successfully"
        }), 200

    except Exception as e:
        print("❌ Tenant logout error:", e)
        if conn and not conn.closed:
            conn.rollback()
        return jsonify({"error": "Logout failed"}), 500
    finally:
        if conn and not conn.closed:
            conn.close()
