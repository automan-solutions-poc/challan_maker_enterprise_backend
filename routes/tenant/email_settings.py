from flask import Blueprint, request, jsonify
from utils.db import get_db_connection
from utils.auth import tenant_token_required
import json

email_settings_bp = Blueprint("email_settings", __name__)

# ------------------------------------
# ✅ Get Tenant Email Settings
# ------------------------------------
@email_settings_bp.route("/email_settings", methods=["GET"])
@tenant_token_required
def get_email_settings():
    try:
        tenant_id = request.tenant.get("tenant_id")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT email_config FROM tenant_settings WHERE tenant_id=%s", (tenant_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row or not row[0]:
            return jsonify({"email_config": {}}), 200

        email_config = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return jsonify({"email_config": email_config}), 200

    except Exception as e:
        print("❌ Error fetching email settings:", e)
        return jsonify({"error": "Failed to fetch email settings"}), 500


# ------------------------------------
# ✅ Update Tenant Email Settings
# ------------------------------------
@email_settings_bp.route("/email_settings", methods=["POST", "PUT"])
@tenant_token_required
def update_email_settings():
    """
    Update SMTP email configuration for a tenant.
    """
    try:
        tenant_id = request.tenant.get("tenant_id")
        data = request.get_json() or {}

        # Mandatory fields
        sender_email = data.get("sender_email")
        sender_password = data.get("sender_password")
        smtp_server = data.get("smtp_server")
        smtp_port = data.get("smtp_port")

        if not all([sender_email, sender_password, smtp_server, smtp_port]):
            return jsonify({"error": "Email, password, SMTP server, and port are required"}), 400

        # Optional fields
        sender_name = data.get("sender_name", "Service Center")
        use_tls = data.get("use_tls", True)
        use_ssl = data.get("use_ssl", False)

        email_config = {
            "sender_name": sender_name,
            "sender_email": sender_email,
            "sender_password": sender_password,
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "use_tls": use_tls,
            "use_ssl": use_ssl
        }

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tenant_settings (tenant_id, email_config, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (tenant_id)
            DO UPDATE SET 
                email_config = EXCLUDED.email_config,
                updated_at = NOW();
        """, (tenant_id, json.dumps(email_config)))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "message": "✅ Email settings updated successfully",
            "email_config": email_config
        }), 200

    except Exception as e:
        print("❌ Error updating email settings:", e)
        return jsonify({"error": "Failed to update email settings"}), 500
