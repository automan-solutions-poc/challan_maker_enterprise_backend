from flask import Blueprint, jsonify
from utils.db import get_db_connection
from utils.auth import admin_token_required

logs_bp = Blueprint("logs", __name__)

@logs_bp.route("/logs", methods=["GET"])
@admin_token_required
def get_logs():
    """Return recent activity logs for dashboard"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, admin_user_id, tenant_id, action_type, description, timestamp
            FROM activity_logs
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        logs = cur.fetchall()
        cur.close()
        conn.close()

        log_list = [
            {
                "id": l[0],
                "admin_user_id": l[1],
                "tenant_id": l[2],
                "action_type": l[3],
                "description": l[4],
                "timestamp": l[5].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for l in logs
        ]

        return jsonify(log_list), 200

    except Exception as e:
        print("❌ Error fetching logs:", e)
        return jsonify({"error": "Failed to fetch logs"}), 500
