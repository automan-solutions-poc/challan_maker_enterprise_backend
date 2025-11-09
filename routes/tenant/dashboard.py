from flask import Blueprint, jsonify, request
from utils.db import get_db_connection
from utils.auth import tenant_token_required

dashboard_bp = Blueprint("tenant_dashboard", __name__)

@dashboard_bp.route("/dashboard", methods=["GET"])
@tenant_token_required
def tenant_dashboard():
    """
    Returns stats for the tenant dashboard:
    - total challans
    - pending challans
    - delivered challans
    """
    try:
        tenant_id = request.tenant.get("tenant_id")

        conn = get_db_connection()
        cur = conn.cursor()

        # Total challans count
        cur.execute("""
            SELECT COUNT(*) FROM challans WHERE tenant_id = %s
        """, (tenant_id,))
        total = cur.fetchone()[0]

        # Pending challans
        cur.execute("""
            SELECT COUNT(*) FROM challans WHERE tenant_id = %s AND status = 'pending'
        """, (tenant_id,))
        pending = cur.fetchone()[0]

        # Delivered challans
        cur.execute("""
            SELECT COUNT(*) FROM challans WHERE tenant_id = %s AND status = 'delivered'
        """, (tenant_id,))
        delivered = cur.fetchone()[0]

        cur.close()
        conn.close()

        return jsonify({
            "total": total,
            "pending": pending,
            "delivered": delivered
        }), 200

    except Exception as e:
        print("❌ Error fetching dashboard data:", e)
        return jsonify({"error": "Failed to fetch dashboard data"}), 500
