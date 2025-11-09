# routes/tenant/challans.py
from flask import Blueprint, request, jsonify
from utils.db import get_db_connection
from utils.auth import tenant_token_required
from datetime import datetime, timedelta
import json
import os
import threading
import random

# utils that you already have in project
from utils.pdf_qr_utils import generate_and_save_qr, generate_pdf
from utils.email_utils import (
    send_challan_email,
    send_otp_email,
    send_delivery_confirmation_email,
)

challans_bp = Blueprint("challans", __name__)

# -----------------------
# Helpers
# -----------------------
def _safe_json_load(v):
    """Return list/dict from JSON-like data or empty list."""
    if v is None:
        return []
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return []

def _safe_json_obj(v):
    """Return dict from JSON-like data or empty dict."""
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {}

def _absolute_static_url(path):
    """Return absolute URL for static resources; returns None for falsy path."""
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    # adjust host/port if deploying elsewhere
    base = request.host_url.rstrip("/")
    # ensure path starts with slash
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"

def _safe_lstrip_path(p):
    """Lstrip leading slash safely, return None if falsy."""
    if not p:
        return None
    return p.lstrip("/")

def _build_qr_payload(challan_record: dict):
    """
    Build QR payload string. Per your request, include all data
    except customer name, customer phone number, and customer city.
    Return JSON string.
    """
    # Copy and remove protected fields
    payload = dict(challan_record)  # shallow copy
    for k in ("customer_name", "contact_number", "city", "email"):
        # remove customer-identifying info except if you want email included — you requested to not include name, phone, city
        if k in payload:
            payload.pop(k, None)
    # Add generated_on timestamp
    payload["qr_generated_at"] = datetime.utcnow().isoformat()
    # Convert non-serializable values
    try:
        return json.dumps(payload, default=str)
    except Exception:
        # fallback: minimal string
        return f"Challan:{payload.get('challan_no','-')}"

# -----------------------
# 1) Send OTP
# -----------------------
@challans_bp.route("/challan/<string:challan_no>/send_otp", methods=["POST"])
@tenant_token_required
def send_otp(challan_no):
    """
    Generate and email OTP to customer's email for pickup verification.
    Request body can contain ttl_minutes (defaults to 2).
    """
    conn = None
    try:
        tenant_id = request.tenant.get("tenant_id")
        body = request.get_json(silent=True) or {}
        ttl_minutes = int(body.get("ttl_minutes", 2))

        otp_code = f"{random.randint(0, 999999):06d}"
        otp_expires = datetime.utcnow() + timedelta(minutes=ttl_minutes)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT customer_name, email FROM challans WHERE challan_no=%s AND tenant_id=%s",
            (challan_no, tenant_id),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return jsonify({"error": "Challan not found"}), 404

        customer_name, email = row
        if not email:
            cur.close()
            conn.close()
            return jsonify({"error": "Customer email missing"}), 400

        cur.execute(
            "UPDATE challans SET otp_code=%s, otp_expires_at=%s WHERE challan_no=%s AND tenant_id=%s",
            (otp_code, otp_expires, challan_no, tenant_id),
        )
        conn.commit()

        # Send email in background
        def _bg_send():
            try:
                send_otp_email(tenant_id, email, customer_name, challan_no, otp_code, ttl_minutes)
            except Exception as e:
                print("❌ Error sending OTP email:", e)

        threading.Thread(target=_bg_send, daemon=True).start()
        cur.close()
        conn.close()

        return jsonify({"message": f"OTP sent to {email}", "expires_in_minutes": ttl_minutes}), 200

    except Exception as e:
        print("❌ send_otp error:", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Failed to send OTP"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

# -----------------------
# 2) Verify OTP & Mark delivered
# -----------------------
@challans_bp.route("/challan/<string:challan_no>/verify_otp", methods=["POST"])
@tenant_token_required
def verify_otp(challan_no):
    """
    Verify the OTP and mark challan delivered. Sends confirmation email with PDF/images if available.
    """
    conn = None
    try:
        tenant_id = request.tenant.get("tenant_id")
        user_id = request.tenant.get("user_id")
        user_name = request.tenant.get("name", "Staff")
        body = request.get_json(silent=True) or {}
        otp_received = (body.get("otp") or "").strip()

        if not otp_received:
            return jsonify({"error": "OTP is required"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT otp_code, otp_expires_at, email, pdf_url, images, customer_name FROM challans WHERE challan_no=%s AND tenant_id=%s",
            (challan_no, tenant_id),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return jsonify({"error": "Challan not found"}), 404

        db_otp, db_otp_expires, customer_email, pdf_url, images_json, customer_name = row

        if not db_otp:
            cur.close()
            conn.close()
            return jsonify({"error": "No OTP generated for this challan. Please generate first."}), 400

        # match
        if otp_received != db_otp:
            cur.close()
            conn.close()
            return jsonify({"error": "Invalid OTP"}), 400

        # expiry
        if db_otp_expires and datetime.utcnow() > db_otp_expires:
            cur.close()
            conn.close()
            return jsonify({"error": "OTP has expired. Please generate a new one."}), 400

        # mark delivered
        delivered_at = datetime.utcnow()
        cur.execute(
            """UPDATE challans
               SET status='delivered',
                   delivered_at=%s,
                   delivered_by=%s,
                   otp_code=NULL,
                   otp_expires_at=NULL,
                   updated_at=NOW()
               WHERE challan_no=%s AND tenant_id=%s""",
            (delivered_at, user_id, challan_no, tenant_id),
        )
        conn.commit()

        # prepare attachments if available
        pdf_file_path = None
        if pdf_url:
            safe_pdf_rel = _safe_lstrip_path(pdf_url)
            if safe_pdf_rel:
                pdf_file_path = os.path.join(os.getcwd(), safe_pdf_rel)
                if not os.path.exists(pdf_file_path):
                    # if not exists, set to None
                    pdf_file_path = None

        image_paths = []
        try:
            imgs = _safe_json_load(images_json)
            for p in imgs:
                rel = _safe_lstrip_path(str(p))
                if rel:
                    full = os.path.join(os.getcwd(), rel)
                    if os.path.exists(full):
                        image_paths.append(full)
        except Exception:
            image_paths = []

        # send confirmation email in background (if email present)
        if customer_email:
            def _bg_confirm():
                try:
                    send_delivery_confirmation_email(
                        tenant_id=tenant_id,
                        to_email=customer_email,
                        customer_name=customer_name,
                        challan_no=challan_no,
                        delivered_at=delivered_at,
                        delivered_by=user_name,
                        pdf_path=pdf_file_path,
                        image_paths=image_paths,
                    )
                except Exception as e:
                    print("❌ delivery confirmation email error:", e)

            threading.Thread(target=_bg_confirm, daemon=True).start()

            # mark email_sent true
            try:
                cur.execute("UPDATE challans SET email_sent=TRUE WHERE challan_no=%s AND tenant_id=%s",
                            (challan_no, tenant_id))
                conn.commit()
            except Exception:
                pass

        cur.close()
        conn.close()

        return jsonify({
            "message": "✅ OTP verified successfully. Challan marked as delivered.",
            "delivered_at": delivered_at.strftime("%Y-%m-%d %H:%M:%S")
        }), 200

    except Exception as e:
        print("❌ verify_otp error:", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Failed to verify OTP"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

# -----------------------
# 3) Get all challans
# -----------------------
@challans_bp.route("/challans", methods=["GET"])
@tenant_token_required
def get_challans():
    """
    Return all challans for the logged-in tenant.
    Date is returned as string "DD/MM/YYYY, hh:mm:ss AM/PM" for frontend.
    """
    try:
        tenant_id = request.tenant.get("tenant_id")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT challan_no, customer_name, serial_number, problem, status, created_at,
                      employee_id, qr_code_url, pdf_url, email_sent
               FROM challans
               WHERE tenant_id=%s
               ORDER BY created_at DESC""",
            (tenant_id,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        challans = []
        for r in rows:
            created_at = r[5]
            created_str = created_at.strftime("%d/%m/%Y, %I:%M:%S %p") if created_at else ""
            challans.append({
                "challan_no": r[0],
                "customer_name": r[1],
                "serial_number": r[2],
                "problem": r[3],
                "status": r[4],
                "date": created_str,
                "employee_id": r[6],
                "qr_code_url": r[7],
                "pdf_url": r[8],
                "email_sent": r[9],
            })

        return jsonify(challans), 200

    except Exception as e:
        print("❌ get_challans error:", e)
        return jsonify({"error": "Failed to fetch challans"}), 500

# -----------------------
# 4) Create new challan
# -----------------------
@challans_bp.route("/challan", methods=["POST"])
@tenant_token_required
def create_challan():
    """
    Create a new challan. Accepts multipart/form-data (images + data) or JSON.
    Generates QR (with payload excluding customer personal fields), PDF, saves DB records,
    and sends email in background if customer email provided.
    """
    conn = None
    try:
        tenant_id = request.tenant.get("tenant_id")
        employee_name = request.tenant.get("name", "Unknown")

        if request.content_type and request.content_type.startswith("multipart/form-data"):
            data_json = request.form.get("data", "{}")
            try:
                data = json.loads(data_json)
            except Exception:
                data = {}
            uploaded_files = request.files.getlist("images")
        else:
            data = request.get_json(silent=True) or {}
            uploaded_files = []

        # required fields
        if not all([data.get("customer_name"), data.get("serial_number"), data.get("problem")]):
            return jsonify({"error": "Missing required fields (customer_name, serial_number, problem)"}), 400

        # challan number
        challan_no = f"CH-{datetime.now().strftime('%d%m%Y%H%M%S')}"

        # handle image uploads (store file paths relative to cwd)
        image_paths = []
        if uploaded_files:
            upload_dir = os.path.join("static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            for f in uploaded_files:
                safe_name = f"{challan_no}_{f.filename}"
                save_path = os.path.join(upload_dir, safe_name)
                f.save(save_path)
                # store relative path for DB, use leading slash
                rel = os.path.join("static", "uploads", safe_name)
                image_paths.append(rel)

        # insert into DB
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO challans (
                   tenant_id, challan_no, customer_name, email, contact_number, serial_number,
                   city, problem, accessories, warranty, dispatch_through, employee_id,
                   items, images, status, created_at, email_sent
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',NOW(),FALSE)""",
            (
                tenant_id,
                challan_no,
                data.get("customer_name"),
                data.get("email"),
                data.get("contact_number"),
                data.get("serial_number"),
                data.get("city"),
                data.get("problem"),
                json.dumps(data.get("accessories", [])),
                data.get("warranty"),
                data.get("dispatch_through"),
                request.tenant.get("user_id"),
                json.dumps(data.get("items", [])),
                json.dumps(image_paths),
            ),
        )
        conn.commit()

        # Build QR payload excluding customer-identifying fields
        # Fetch a little more context to include useful data
        qr_record = {
            "challan_no": challan_no,
            "tenant_id": tenant_id,
            "serial_number": data.get("serial_number"),
            "problem": data.get("problem"),
            "items": data.get("items", []),
            "accessories": data.get("accessories", []),
            "warranty": data.get("warranty"),
            "dispatch_through": data.get("dispatch_through"),
            "created_at": datetime.utcnow().isoformat(),
        }
        qr_payload = _build_qr_payload(qr_record)

        # generate and save qr
        try:
            qr_path = generate_and_save_qr(qr_payload)
            # make absolute for DB and client
            qr_url = _absolute_static_url(qr_path) if qr_path else None
        except Exception as e:
            print("⚠️ QR generation failed:", e)
            qr_url = None

        # fetch tenant settings for design
        cur.execute("SELECT branding_config, challan_config FROM tenant_settings WHERE tenant_id=%s", (tenant_id,))
        ts_row = cur.fetchone()
        branding = _safe_json_obj(ts_row[0]) if ts_row else {}
        challan_cfg = _safe_json_obj(ts_row[1]) if ts_row else {}
        tenant_design = {**challan_cfg, **branding}
        if tenant_design.get("logo_url"):
            tenant_design["logo_url"] = _absolute_static_url(tenant_design["logo_url"])

        # prepare pdf data, images for PDF should be absolute URLs
        pdf_data = {
            "challan_no": challan_no,
            "customer_name": data.get("customer_name"),
            "email": data.get("email"),
            "contact_number": data.get("contact_number"),
            "serial_number": data.get("serial_number"),
            "city": data.get("city"),
            "problem": data.get("problem"),
            "accessories": data.get("accessories", []),
            "warranty": data.get("warranty"),
            "dispatch_through": data.get("dispatch_through"),
            "employee_name": employee_name,
            "items": data.get("items", []),
            "status": "pending",
            "images": [_absolute_static_url(p) for p in image_paths],
            "qr_code_url": qr_url,
            "generated_on": datetime.utcnow().isoformat(),
        }

        # generate PDF (helper should return relative path e.g. /static/pdfs/CH-...pdf)
        try:
            pdf_rel = generate_pdf(pdf_data, tenant_design)
        except Exception as e:
            # if pdf generation fails, keep process going but warn
            print("❌ Error generating PDF:", e)
            pdf_rel = None

        # update DB with qr and pdf urls (store absolute or relative - prefer relative in DB, absolute for client)
        db_qr = qr_url if qr_url else None
        db_pdf = pdf_rel if pdf_rel else None
        try:
            cur.execute("UPDATE challans SET qr_code_url=%s, pdf_url=%s WHERE challan_no=%s",
                        (db_qr, db_pdf, challan_no))
            conn.commit()
        except Exception as e:
            print("⚠️ Could not update qr/pdf in DB:", e)

        # send email asynchronously if email present & pdf exists
        if data.get("email") and pdf_rel:
            pdf_full_path = None
            safe_rel = _safe_lstrip_path(pdf_rel)
            if safe_rel:
                candidate = os.path.join(os.getcwd(), safe_rel)
                if os.path.exists(candidate):
                    pdf_full_path = candidate
            # fire-and-forget
            def _bg_send_mail():
                try:
                    send_challan_email(tenant_id, data["email"], pdf_data, pdf_full_path, [os.path.join(os.getcwd(), _safe_lstrip_path(p)) for p in image_paths])
                except Exception as e:
                    print("❌ send_challan_email error:", e)
            threading.Thread(target=_bg_send_mail, daemon=True).start()
            # mark email_sent true
            try:
                cur.execute("UPDATE challans SET email_sent=TRUE WHERE challan_no=%s", (challan_no,))
                conn.commit()
            except Exception:
                pass

        cur.close()
        conn.close()

        return jsonify({
            "message": "✅ Challan created",
            "challan_no": challan_no,
            "pdf_url": pdf_rel,
            "qr_url": qr_url,
        }), 201

    except Exception as e:
        print("❌ create_challan error:", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Failed to create challan"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

# -----------------------
# 5) Update challan
# -----------------------
@challans_bp.route("/challan/<string:challan_no>", methods=["PUT"])
@tenant_token_required
def update_challan(challan_no):
    """
    Update challan fields (supports multipart form with images or JSON).
    Regenerates PDF and optionally re-sends email.
    """
    conn = None
    try:
        tenant_id = request.tenant.get("tenant_id")
        employee_name = request.tenant.get("name", "Unknown")

        if request.content_type and request.content_type.startswith("multipart/form-data"):
            data_json = request.form.get("data", "{}")
            try:
                data = json.loads(data_json)
            except Exception:
                data = {}
            uploaded_files = request.files.getlist("images")
        else:
            data = request.get_json(silent=True) or {}
            uploaded_files = []

        # Save new uploaded images
        image_paths = []
        if uploaded_files:
            upload_dir = os.path.join("static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            for f in uploaded_files:
                safe_name = f"{challan_no}_{f.filename}"
                save_path = os.path.join(upload_dir, safe_name)
                f.save(save_path)
                image_paths.append(os.path.join("static", "uploads", safe_name))

        conn = get_db_connection()
        cur = conn.cursor()

        # get old pdf (to optionally remove)
        cur.execute("SELECT pdf_url FROM challans WHERE challan_no=%s AND tenant_id=%s", (challan_no, tenant_id))
        old_pdf_row = cur.fetchone()
        old_pdf = old_pdf_row[0] if old_pdf_row else None

        # update record
        cur.execute(
            """UPDATE challans SET customer_name=%s, email=%s, contact_number=%s, serial_number=%s, city=%s,
               problem=%s, accessories=%s, warranty=%s, dispatch_through=%s, items=%s, images=%s,
               updated_at=NOW(), email_sent=FALSE
               WHERE challan_no=%s AND tenant_id=%s""",
            (
                data.get("customer_name"),
                data.get("email"),
                data.get("contact_number"),
                data.get("serial_number"),
                data.get("city"),
                data.get("problem"),
                json.dumps(data.get("accessories", [])),
                data.get("warranty"),
                data.get("dispatch_through"),
                json.dumps(data.get("items", [])),
                json.dumps(image_paths),
                challan_no,
                tenant_id,
            ),
        )
        conn.commit()

        # remove old pdf file if it exists and new pdf will be created
        if old_pdf:
            safe_rel = _safe_lstrip_path(old_pdf)
            if safe_rel:
                candidate = os.path.join(os.getcwd(), safe_rel)
                try:
                    if os.path.exists(candidate):
                        os.remove(candidate)
                except Exception as e:
                    print("⚠️ Could not remove old pdf:", e)

        # fetch tenant design
        cur.execute("SELECT branding_config, challan_config FROM tenant_settings WHERE tenant_id=%s", (tenant_id,))
        ts_row = cur.fetchone()
        branding = _safe_json_obj(ts_row[0]) if ts_row else {}
        challan_cfg = _safe_json_obj(ts_row[1]) if ts_row else {}
        tenant_design = {**challan_cfg, **branding}
        if tenant_design.get("logo_url"):
            tenant_design["logo_url"] = _absolute_static_url(tenant_design["logo_url"])

        # prepare data for PDF
        pdf_data = {
            "challan_no": challan_no,
            "customer_name": data.get("customer_name"),
            "email": data.get("email"),
            "contact_number": data.get("contact_number"),
            "serial_number": data.get("serial_number"),
            "city": data.get("city"),
            "problem": data.get("problem"),
            "accessories": data.get("accessories", []),
            "warranty": data.get("warranty"),
            "dispatch_through": data.get("dispatch_through"),
            "employee_name": employee_name,
            "items": data.get("items", []),
            "status": data.get("status", "pending"),
            "images": [_absolute_static_url(p) for p in image_paths],
            "created_at": datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
        }

        # generate pdf
        try:
            pdf_rel = generate_pdf(pdf_data, tenant_design)
        except Exception as e:
            print("❌ Error generating PDF on update:", e)
            pdf_rel = None

        if pdf_rel:
            try:
                cur.execute("UPDATE challans SET pdf_url=%s WHERE challan_no=%s AND tenant_id=%s",
                            (pdf_rel, challan_no, tenant_id))
                conn.commit()
            except Exception:
                pass

        # optionally email updated pdf to customer
        if data.get("email") and pdf_rel:
            # resolve full path
            pdf_full_path = None
            safe_rel = _safe_lstrip_path(pdf_rel)
            if safe_rel:
                candidate = os.path.join(os.getcwd(), safe_rel)
                if os.path.exists(candidate):
                    pdf_full_path = candidate
            def _bg_resend():
                try:
                    send_challan_email(tenant_id, data.get("email"), pdf_data, pdf_full_path, [os.path.join(os.getcwd(), _safe_lstrip_path(p)) for p in image_paths])
                except Exception as e:
                    print("❌ resend email error:", e)
            threading.Thread(target=_bg_resend, daemon=True).start()
            try:
                cur.execute("UPDATE challans SET email_sent=TRUE WHERE challan_no=%s", (challan_no,))
                conn.commit()
            except Exception:
                pass

        cur.close()
        conn.close()
        return jsonify({"message": "✅ Challan updated, PDF regenerated (if possible)"}), 200

    except Exception as e:
        print("❌ update_challan error:", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Failed to update challan"}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

# -----------------------
# 6) Delete challan
# -----------------------
@challans_bp.route("/challan/<string:challan_no>", methods=["DELETE"])
@tenant_token_required
def delete_challan(challan_no):
    """Delete challan for tenant."""
    try:
        tenant_id = request.tenant.get("tenant_id")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM challans WHERE challan_no=%s AND tenant_id=%s", (challan_no, tenant_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "🗑️ Challan deleted successfully"}), 200
    except Exception as e:
        print("❌ delete_challan error:", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify({"error": "Failed to delete challan"}), 500

# -----------------------
# 7) Get single challan (for edit)
# -----------------------
@challans_bp.route("/challan/<string:challan_no>", methods=["GET"])
@tenant_token_required
def get_single_challan(challan_no):
    """Fetch a single challan record for editing/viewing."""
    try:
        tenant_id = request.tenant.get("tenant_id")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT challan_no, customer_name, email, contact_number, serial_number, city, problem,
                      accessories, warranty, dispatch_through, employee_id, items, status, created_at,
                      qr_code_url, pdf_url, images
               FROM challans WHERE challan_no=%s AND tenant_id=%s""",
            (challan_no, tenant_id),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify({"error": "Challan not found"}), 404

        def _format_datetime(v):
            if not v:
                return None
            try:
                return v.strftime("%d/%m/%Y, %I:%M:%S %p")
            except Exception:
                return str(v)

        challan = {
            "challan_no": row[0],
            "customer_name": row[1],
            "email": row[2],
            "contact_number": row[3],
            "serial_number": row[4],
            "city": row[5],
            "problem": row[6],
            "accessories": _safe_json_load(row[7]),
            "warranty": row[8],
            "dispatch_through": row[9],
            "employee_id": row[10],
            "items": _safe_json_load(row[11]),
            "status": row[12],
            "created_at": _format_datetime(row[13]),
            "qr_code_url": row[14],
            "pdf_url": row[15],
            "images": _safe_json_load(row[16]),
        }

        return jsonify(challan), 200

    except Exception as e:
        print("❌ get_single_challan error:", e)
        return jsonify({"error": "Failed to fetch challan"}), 500
