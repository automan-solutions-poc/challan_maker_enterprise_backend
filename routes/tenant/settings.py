from flask import Blueprint, request, jsonify
from utils.db import get_db_connection
from utils.auth import tenant_token_required
import json
import os
from werkzeug.utils import secure_filename

tenant_settings_bp = Blueprint("tenant_settings", __name__)
upload_bp = Blueprint("upload", __name__)

# ------------------------------------
# ✅ SAFE JSON HANDLER
# ------------------------------------
def safe_json(value):
    """Safely load JSON whether it's dict, string, bytes, or None."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    try:
        return json.loads(value)
    except Exception:
        return {}

# ------------------------------------
# ✅ GET Tenant Settings (Branding + Challan + Tenant Email)
# ------------------------------------
@tenant_settings_bp.route("/settings", methods=["GET"])
@tenant_token_required
def get_tenant_settings():
    """Fetch branding (design), challan settings, and tenant email (read-only)"""
    try:
        tenant_id = request.tenant.get("tenant_id")

        conn = get_db_connection()
        cur = conn.cursor()

        # ✅ Fetch tenant settings + email from tenant table
        cur.execute("""
            SELECT 
                ts.branding_config, 
                ts.challan_config,
                t.email
            FROM tenants t
            LEFT JOIN tenant_settings ts ON ts.tenant_id = t.id
            WHERE t.id = %s
        """, (tenant_id,))

        row = cur.fetchone()
        cur.close()
        conn.close()

        # ✅ Handle missing record gracefully
        if not row:
            return jsonify({
                "branding": {},
                "challan": {},
                "tenant_email": None
            }), 200

        branding = safe_json(row[0])
        challan = safe_json(row[1])
        tenant_email = row[2] if len(row) > 2 else None

        # ✅ Add email to branding as read-only field for frontend
        if tenant_email:
            branding["company_email"] = tenant_email

        return jsonify({
            "branding": branding,
            "challan": challan,
            "tenant_email": tenant_email
        }), 200

    except Exception as e:
        print(f"❌ Error fetching tenant settings: {type(e).__name__} - {e}")
        return jsonify({"error": "Failed to fetch tenant settings"}), 500


# ------------------------------------
# ✅ UPDATE Tenant Settings
# ------------------------------------
@tenant_settings_bp.route("/settings", methods=["POST", "PUT"])
@tenant_token_required
def update_tenant_settings():
    """Update tenant's branding and challan configuration"""
    try:
        tenant_id = request.tenant.get("tenant_id")
        data = request.get_json(silent=True) or {}

        branding = safe_json(data.get("branding"))
        challan = safe_json(data.get("challan"))

        if not branding and not challan:
            return jsonify({"error": "Missing branding or challan data"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        # ✅ UPSERT logic for tenant settings
        cur.execute("""
            INSERT INTO tenant_settings (tenant_id, branding_config, challan_config, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (tenant_id)
            DO UPDATE SET 
                branding_config = EXCLUDED.branding_config,
                challan_config = EXCLUDED.challan_config,
                updated_at = NOW();
        """, (tenant_id, json.dumps(branding), json.dumps(challan)))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "✅ Settings updated successfully"}), 200

    except Exception as e:
        print(f"❌ Error updating tenant settings: {type(e).__name__} - {e}")
        return jsonify({"error": "Failed to update tenant settings"}), 500


# ------------------------------------
# ✅ DELETE Tenant Settings
# ------------------------------------
@tenant_settings_bp.route("/settings", methods=["DELETE"])
@tenant_token_required
def delete_tenant_settings():
    """Clear tenant design settings (useful for resetting template)"""
    try:
        tenant_id = request.tenant.get("tenant_id")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM tenant_settings WHERE tenant_id=%s", (tenant_id,))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "🗑️ Settings cleared successfully"}), 200

    except Exception as e:
        print(f"❌ Error deleting tenant settings: {type(e).__name__} - {e}")
        return jsonify({"error": "Failed to delete settings"}), 500


# ------------------------------------
# ✅ UPLOAD Tenant Logo
# ------------------------------------
UPLOAD_FOLDER = os.path.join(os.getcwd(), "static", "logos")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
@upload_bp.route("/upload_logo", methods=["POST"])
@tenant_token_required
def upload_logo():
    """Upload and save tenant logo, return full accessible URL"""
    try:
        tenant_id = request.tenant.get("tenant_id")
        file = request.files.get("logo")

        if not file:
            return jsonify({"error": "No file uploaded"}), 400

        from werkzeug.utils import secure_filename
        filename = secure_filename(f"tenant_{tenant_id}_{file.filename}")
        upload_folder = os.path.join(os.getcwd(), "static", "logos")
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)

        # ✅ Construct full public URL
        base_url = request.host_url.rstrip('/')
        public_url = f"{base_url}/static/logos/{filename}"

        # ✅ Update in DB
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE tenant_settings
            SET branding_config = jsonb_set(
                COALESCE(branding_config, '{}'::jsonb),
                '{logo_url}', %s::jsonb, true
            )
            WHERE tenant_id = %s
        """, (json.dumps(public_url), tenant_id))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "message": "✅ Logo uploaded successfully",
            "logo_url": public_url
        }), 200

    except Exception as e:
        print("❌ Logo upload failed:", e)
        return jsonify({"error": "Failed to upload logo"}), 500



@tenant_settings_bp.route("/design", methods=["GET"])
@tenant_token_required
def get_merged_tenant_design():
    """
    Returns a merged view of tenant's branding + challan settings.
    Used for live preview.
    """
    try:
        tenant_id = request.tenant.get("tenant_id")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT branding_config, challan_config
            FROM tenant_settings
            WHERE tenant_id=%s
        """, (tenant_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        def safe_json(v):
            if not v:
                return {}
            if isinstance(v, dict):
                return v
            try:
                return json.loads(v)
            except:
                return {}

        branding = safe_json(row[0]) if row else {}
        challan = safe_json(row[1]) if row else {}

        merged = {**challan, **branding}

        return jsonify({"design": merged}), 200

    except Exception as e:
        print("❌ Error loading merged design:", e)
        return jsonify({"error": "Failed to load tenant design"}), 500
    