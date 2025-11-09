import os
import json
import time
from flask_mail import Message, Mail
from flask import current_app
from utils.db import get_db_connection
from app import mail as global_mail
from app import create_app  # Avoid circular import
from flask_mail import Mail, Message
import time
import os


def get_tenant_mail_config(tenant_id):
    """Fetch tenant-specific SMTP credentials from DB."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT email_config FROM tenant_settings WHERE tenant_id=%s", (tenant_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row or not row[0]:
            print(f"⚠️ No email settings found for tenant {tenant_id}")
            return None

        if isinstance(row[0], dict):
            return row[0]
        return json.loads(row[0])
    except Exception as e:
        print("❌ Error fetching tenant email config:", e)
        return None


def send_challan_email(tenant_id, to_email, challan_data, pdf_path, image_paths=[]):
    """
    Sends challan email with PDF + image attachments.
    Supports tenant-based SMTP credentials + retry mechanism.
    """
    from app import create_app  # ✅ Import here to avoid circular dependency

    try:
        app = create_app()  # Create new Flask app for context
        tenant_mail_cfg = get_tenant_mail_config(tenant_id)

        # ✅ Configure tenant mail if available
        if tenant_mail_cfg and tenant_mail_cfg.get("sender_email") and tenant_mail_cfg.get("sender_password"):
            print(f"📧 Using tenant-specific email: {tenant_mail_cfg['sender_email']}")
            mail_instance = Mail()
            app.config.update({
                "MAIL_SERVER": tenant_mail_cfg.get("mail_server", "smtp.gmail.com"),
                "MAIL_PORT": tenant_mail_cfg.get("mail_port", 587),
                "MAIL_USE_TLS": tenant_mail_cfg.get("use_tls", True),
                "MAIL_USERNAME": tenant_mail_cfg["sender_email"],
                "MAIL_PASSWORD": tenant_mail_cfg["sender_password"],
                "MAIL_DEFAULT_SENDER": (
                    tenant_mail_cfg.get("sender_name", "Service Center"),
                    tenant_mail_cfg["sender_email"]
                ),
            })
            mail_instance.init_app(app)
        else:
            print("⚠️ Tenant email not configured — using global sender.")
            mail_instance = global_mail

        with app.app_context():
            msg = Message(
                subject=f"Challan - {challan_data.get('challan_no', '')}",
                recipients=[to_email],
            )

            # 🧾 Email Body
            msg.html = f"""
            <div style='font-family: Arial, sans-serif; color: #333'>
                <h3>Dear {challan_data.get('customer_name', 'Customer')},</h3>
                <p>Your service challan has been successfully created/updated.</p>
                <p><b>Challan No:</b> {challan_data.get('challan_no')}<br/>
                <b>Problem:</b> {challan_data.get('problem')}<br/>
                <b>Serial No:</b> {challan_data.get('serial_number')}<br/>
                <b>Accessories:</b> {', '.join(challan_data.get('accessories', []))}</p>
                <p>Please find attached your challan PDF and related images.</p>
                <p>Regards,<br/><b>{challan_data.get('company_name', 'Service Center')}</b></p>
            </div>
            """

            # 📎 Attach PDF
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    msg.attach(os.path.basename(pdf_path), "application/pdf", f.read())

            # 📷 Attach images
            for img_path in image_paths:
                if img_path and os.path.exists(img_path):
                    with open(img_path, "rb") as f:
                        msg.attach(os.path.basename(img_path), "image/jpeg", f.read())

            # 🌀 Retry Mechanism (3 attempts)
            max_retries = 3
            delay_seconds = 5
            for attempt in range(1, max_retries + 1):
                try:
                    mail_instance.send(msg)
                    print(f"✅ Email sent successfully to {to_email} (Attempt {attempt})")
                    return True
                except Exception as e:
                    print(f"⚠️ Attempt {attempt} failed: {e}")
                    if attempt < max_retries:
                        print(f"⏳ Retrying in {delay_seconds} seconds...")
                        time.sleep(delay_seconds)
                    else:
                        print("❌ All attempts failed. Email not sent.")
                        return False

    except Exception as e:
        print("❌ Fatal email sending error:", e)
        return False


# ---------------------------------------------------------------------
# 🔐 NEW: Send OTP Email
# ---------------------------------------------------------------------
def send_otp_email(tenant_id, to_email, customer_name, challan_no, otp_code, ttl_minutes=10):
    """
    Sends an OTP email to the customer when verifying pickup.
    """
    from app import create_app  # avoid circular import

    try:
        app = create_app()
        tenant_mail_cfg = get_tenant_mail_config(tenant_id)

        # ✅ Configure tenant-specific mail
        if tenant_mail_cfg and tenant_mail_cfg.get("sender_email") and tenant_mail_cfg.get("sender_password"):
            mail_instance = Mail()
            app.config.update({
                "MAIL_SERVER": tenant_mail_cfg.get("mail_server", "smtp.gmail.com"),
                "MAIL_PORT": tenant_mail_cfg.get("mail_port", 587),
                "MAIL_USE_TLS": tenant_mail_cfg.get("use_tls", True),
                "MAIL_USERNAME": tenant_mail_cfg["sender_email"],
                "MAIL_PASSWORD": tenant_mail_cfg["sender_password"],
                "MAIL_DEFAULT_SENDER": (
                    tenant_mail_cfg.get("sender_name", "Service Center"),
                    tenant_mail_cfg["sender_email"]
                ),
            })
            mail_instance.init_app(app)
        else:
            print("⚠️ Tenant email not configured — using global sender.")
            mail_instance = global_mail

        with app.app_context():
            msg = Message(
                subject=f"🔐 OTP for Challan {challan_no}",
                recipients=[to_email],
            )

            msg.html = f"""
            <div style='font-family: Arial, sans-serif; color: #333'>
                <h3>Dear {customer_name or 'Customer'},</h3>
                <p>Your device associated with <b>Challan No: {challan_no}</b> is ready for collection.</p>
                <p>Please use the following One-Time Password (OTP) to verify your identity at pickup:</p>
                <div style='background:#f5f5f5;padding:10px 20px;border:1px dashed #aaa;
                    display:inline-block;font-size:20px;font-weight:bold;color:#000;margin:10px 0;'>
                    {otp_code}
                </div>
                <p>This OTP will expire in <b>{ttl_minutes} minutes</b>.</p>
                <p>If you did not request this, please ignore this email or contact our support.</p>
                <p>Regards,<br/><b>{tenant_mail_cfg.get('sender_name', 'Service Center')}</b></p>
            </div>
            """

            # 🌀 Retry Mechanism (3 attempts)
            max_retries = 3
            delay_seconds = 5
            for attempt in range(1, max_retries + 1):
                try:
                    mail_instance.send(msg)
                    print(f"✅ OTP email sent successfully to {to_email} (Attempt {attempt})")
                    return True
                except Exception as e:
                    print(f"⚠️ Attempt {attempt} failed: {e}")
                    if attempt < max_retries:
                        print(f"⏳ Retrying in {delay_seconds} seconds...")
                        time.sleep(delay_seconds)
                    else:
                        print("❌ All attempts failed. OTP email not sent.")
                        return False

    except Exception as e:
        print("❌ Error sending OTP email:", e)
        return False
    
    
    
    
    
    
def send_delivery_confirmation_email(tenant_id, to_email, customer_name, challan_no, delivered_at, delivered_by, pdf_path=None, image_paths=None):
    """
    Sends a delivery confirmation email to the customer after OTP verification.
    """
  
    try:
        app = create_app()
        tenant_mail_cfg = get_tenant_mail_config(tenant_id)
        image_paths = image_paths or []

        # ✅ Configure tenant mail
        if tenant_mail_cfg and tenant_mail_cfg.get("sender_email") and tenant_mail_cfg.get("sender_password"):
            mail_instance = Mail()
            app.config.update({
                "MAIL_SERVER": tenant_mail_cfg.get("mail_server", "smtp.gmail.com"),
                "MAIL_PORT": tenant_mail_cfg.get("mail_port", 587),
                "MAIL_USE_TLS": tenant_mail_cfg.get("use_tls", True),
                "MAIL_USERNAME": tenant_mail_cfg["sender_email"],
                "MAIL_PASSWORD": tenant_mail_cfg["sender_password"],
                "MAIL_DEFAULT_SENDER": (
                    tenant_mail_cfg.get("sender_name", "Service Center"),
                    tenant_mail_cfg["sender_email"]
                ),
            })
            mail_instance.init_app(app)
        else:
            print("⚠️ Tenant email not configured — using global sender.")
            mail_instance = global_mail

        with app.app_context():
            msg = Message(
                subject=f"✅ Delivery Confirmation - Challan {challan_no}",
                recipients=[to_email],
            )

            # 💌 Email body
            msg.html = f"""
            <div style="font-family: Arial, sans-serif; color: #333;">
                <h3>Dear {customer_name or 'Customer'},</h3>
                <p>
                    We are pleased to inform you that your device associated with 
                    <strong>Challan No:</strong> {challan_no} has been successfully delivered.
                </p>
                <p>
                    <strong>Delivered By:</strong> {delivered_by}<br>
                    <strong>Date:</strong> {delivered_at.strftime('%d/%m/%Y, %I:%M %p')}
                </p>
                <p>Attached is your service challan and related images for your records.</p>
                <p style="margin-top:20px;">
                    Thank you for trusting <b>{tenant_mail_cfg.get('sender_name', 'our service center')}</b>!<br>
                    We look forward to serving you again.
                </p>
                <hr>
                <small style="color:#777;">This is an automated confirmation email. Please do not reply.</small>
            </div>
            """

            # 📎 Attach PDF if exists
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    msg.attach(os.path.basename(pdf_path), "application/pdf", f.read())

            # 📸 Attach images if available
            for img_path in image_paths:
                if img_path and os.path.exists(img_path):
                    with open(img_path, "rb") as f:
                        msg.attach(os.path.basename(img_path), "image/jpeg", f.read())

            # 🌀 Retry mechanism
            max_retries = 3
            delay_seconds = 5
            for attempt in range(1, max_retries + 1):
                try:
                    mail_instance.send(msg)
                    print(f"✅ Delivery confirmation email sent to {to_email} (Attempt {attempt})")
                    return True
                except Exception as e:
                    print(f"⚠️ Attempt {attempt} failed: {e}")
                    if attempt < max_retries:
                        print(f"⏳ Retrying in {delay_seconds} seconds...")
                        time.sleep(delay_seconds)
                    else:
                        print("❌ All attempts failed. Delivery confirmation email not sent.")
                        return False

    except Exception as e:
        print("❌ Error sending delivery confirmation email:", e)
        return False
