from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from utils.db import get_db_connection
import jwt
import os
from datetime import datetime, timedelta
import psycopg2.extras

admin_auth_bp = Blueprint("admin_auth", __name__)

# ==============================================================
# 🔹 In-memory token blacklist (for logged-out tokens)
# ==============================================================
TOKEN_BLACKLIST = set()

# ==============================================================
# 🔹 Helper: Generate JWT Token
# ==============================================================
def generate_admin_token(admin_data):
    secret = os.getenv("ADMIN_JWT_SECRET", "super_secure_admin_secret")
    exp_hours = int(os.getenv("ADMIN_JWT_EXP_HOURS", 8))

    payload = {
        "admin_id": admin_data["id"],
        "email": admin_data["email"],
        "role": admin_data["role"],
        "is_superadmin": admin_data["is_superadmin"],
        "exp": datetime.utcnow() + timedelta(hours=exp_hours)
    }

    return jwt.encode(payload, secret, algorithm="HS256")


# ==============================================================
# 🧑‍💼 Admin Login
# ==============================================================
@admin_auth_bp.route("/login", methods=["POST"])
def admin_login():
    conn = None
    try:
        data = request.get_json()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT * FROM admin_users WHERE email=%s", (email,))
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Admin not found"}), 404

        # ✅ Validate password
        if not check_password_hash(row["password_hash"], password):
            return jsonify({"error": "Invalid credentials"}), 401

        # ✅ Check active status
        if not row["is_active"]:
            return jsonify({"error": "Account is inactive. Contact support."}), 403

        # ✅ Generate JWT
        token = generate_admin_token(row)

        cur.close()
        conn.close()

        return jsonify({
            "message": "Login successful",
            "token": token,
            "admin": {
                "id": row["id"],
                "full_name": row["full_name"],
                "email": row["email"],
                "role": row["role"],
                "is_superadmin": row["is_superadmin"]
            }
        }), 200

    except Exception as e:
        print("❌ Error during admin login:", e)
        if conn and not conn.closed:
            conn.rollback()
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn and not conn.closed:
            conn.close()


# ==============================================================
# 🆕 Create Admin (Superadmin only)
# ==============================================================
@admin_auth_bp.route("/create", methods=["POST"])
def create_admin():
    conn = None
    try:
        data = request.get_json()
        full_name = (data.get("full_name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password")
        role = data.get("role", "admin")
        is_superadmin = data.get("is_superadmin", False)

        if not all([full_name, email, password]):
            return jsonify({"error": "All fields are required"}), 400

        hashed_pw = generate_password_hash(password)

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT id FROM admin_users WHERE email=%s", (email,))
        if cur.fetchone():
            return jsonify({"error": "Email already exists"}), 409

        cur.execute("""
            INSERT INTO admin_users (full_name, email, password_hash, role, is_superadmin, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
            RETURNING id, full_name, email, role, is_superadmin
        """, (full_name, email, hashed_pw, role, is_superadmin))

        new_admin = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "message": "✅ Admin user created successfully",
            "admin": new_admin
        }), 201

    except Exception as e:
        print("❌ Error creating admin:", e)
        if conn and not conn.closed:
            conn.rollback()
        return jsonify({"error": "Failed to create admin"}), 500
    finally:
        if conn and not conn.closed:
            conn.close()


# ==============================================================
# 🚪 Admin Logout
# ==============================================================
@admin_auth_bp.route("/logout", methods=["POST"])
def admin_logout():
    """Logout by blacklisting the JWT token."""
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 400

        token = auth_header.split(" ")[1]
        TOKEN_BLACKLIST.add(token)  # Add token to blacklist
        return jsonify({"message": "✅ Logged out successfully"}), 200

    except Exception as e:
        print("❌ Logout error:", e)
        return jsonify({"error": "Failed to logout"}), 500


# ==============================================================
# 🔒 Token Validation Helper (Optional Use)
# ==============================================================
def is_token_blacklisted(token: str) -> bool:
    """Check if a token is blacklisted"""
    return token in TOKEN_BLACKLIST
