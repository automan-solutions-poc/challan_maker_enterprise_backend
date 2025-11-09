from flask import Blueprint, jsonify
from utils.db import get_db_connection
from utils.auth import admin_token_required

# ✅ Blueprint renamed for clarity
admin_dashboard_bp = Blueprint("admin_dashboard", __name__)

# ============================================================
# 📊 Admin Dashboard Summary Endpoint
# ============================================================
@admin_dashboard_bp.route("/dashboard/summary", methods=["GET"])
@admin_token_required
def admin_dashboard_summary():
    """
    Returns summarized admin dashboard data:
      - Total active tenants
      - Total active tenant users
      - Total active subscriptions
      - Recent 10 activity logs
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # -------------------------------
        # 🧾 Count Active Tenants
        # -------------------------------
        cur.execute("SELECT COUNT(*) FROM tenants WHERE status = 'active'")
        active_tenants = cur.fetchone()[0]

        # -------------------------------
        # 👥 Count Active Tenant Users
        # -------------------------------
        cur.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
        active_users = cur.fetchone()[0]

        # -------------------------------
        # 💳 Count Active Subscriptions
        # -------------------------------
        cur.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active = TRUE")
        active_subs = cur.fetchone()[0]

        # -------------------------------
        # 🕓 Fetch Recent Activity Logs
        # -------------------------------
        cur.execute("""
            SELECT action_type, description, timestamp
            FROM activity_logs
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        logs = [
            {
                "action_type": r[0],
                "description": r[1],
                "timestamp": r[2].strftime("%Y-%m-%d %H:%M:%S")
            }
            for r in cur.fetchall()
        ]

        cur.close()
        conn.close()

        return jsonify({
            "tenants": active_tenants,
            "users": active_users,
            "subscriptions": active_subs,
            "logs": logs
        }), 200

    except Exception as e:
        print("❌ Error in admin_dashboard_summary:", e)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to fetch dashboard data"}), 500
    finally:
        if conn:
            conn.close()
