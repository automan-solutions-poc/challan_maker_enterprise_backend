import qrcode
from fpdf import FPDF
import os
from datetime import datetime
import requests
from io import BytesIO
import json
import pdfkit
from jinja2 import Environment, FileSystemLoader

# Ensure folders exist
os.makedirs("static/qr_codes", exist_ok=True)
os.makedirs("static/pdfs", exist_ok=True)
# baselocation_url="http://192.168.1.12:6001"
baselocation_url="http://127.0.0.1:6001"
# ----------------------------------------------------
# 🔹 Generate QR Code and Save
# ----------------------------------------------------


def generate_and_save_qr(challan_no, challan_data=None):
    """
    Generate a hybrid QR code that includes:
    - Non-sensitive challan data (for offline use)
    - A tracking URL (for online redirection)

    Returns the relative URL (e.g., /static/qr_codes/CH-23102025100132.png)
    """
    try:
        os.makedirs("static/qr_codes", exist_ok=True)

        # 🧠 Build QR payload (exclude sensitive customer data)
        qr_payload = {
            "challan_no": challan_no,
            "serial_number": challan_data.get("serial_number") if challan_data else None,
            "problem": challan_data.get("problem") if challan_data else None,
            "accessories": challan_data.get("accessories", []) if challan_data else [],
            "warranty": challan_data.get("warranty") if challan_data else None,
            "dispatch_through": challan_data.get("dispatch_through") if challan_data else None,
            "status": challan_data.get("status", "Pending") if challan_data else "Pending",
            "items": challan_data.get("items", []) if challan_data else [],
        }

        # 🌐 Add tracking URL
        # tracking_url = f"https://automan.app/track/{challan_no}"

        qr_content = {
            # "tracking_url": tracking_url,
            "data": qr_payload
        }

        # ✅ Convert to compact JSON
        qr_text = json.dumps(qr_content, indent=None, separators=(",", ":"))

        # ✅ Generate QR
        qr_img = qrcode.make(qr_text)

        # ✅ Save QR code
        filename = f"{challan_no}.png"
        filepath = os.path.join("static/qr_codes", filename)
        qr_img.save(filepath)

        print(f"✅ QR generated for {challan_no} ")
        return f"/static/qr_codes/{filename}"

    except Exception as e:
        print("❌ QR Generation Error:", e)
        return None


# ----------------------------------------------------
# 🧾 OLD FPDF VERSION (Kept for reference)
# ----------------------------------------------------
# def generate_pdf(data, tenant_design):
#     """
#     Generates a PDF challan and saves it under /static/pdfs/.
#     Adds company logo (if available) and 'DELIVERED' watermark if applicable.
#     Returns the relative URL (e.g., /static/pdfs/CH-23102025100132.pdf)
#     """
#     try:
#         # --- Setup directories ---
#         base_dir = os.path.dirname(os.path.abspath(__file__))
#         static_dir = os.path.join(base_dir, "..", "static", "pdfs")
#         os.makedirs(static_dir, exist_ok=True)

#         # --- PDF path ---
#         filename = f"{data['challan_no']}.pdf"
#         file_path = os.path.join(static_dir, filename)
#         relative_url = f"/static/pdfs/{filename}"

#         # --- Tenant theme color ---
#         theme_color = tenant_design.get("theme_color", "#114e9e")
#         try:
#             r, g, b = tuple(int(theme_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
#         except Exception:
#             r, g, b = (17, 78, 158)

#         # --- Create PDF ---
#         pdf = FPDF()
#         pdf.add_page()
#         pdf.set_auto_page_break(auto=True, margin=15)

#         # --- Watermark if delivered ---
#         if data.get("status", "").lower() == "delivered":
#             pdf.set_text_color(200, 200, 200)
#             pdf.set_font("Arial", "B", 60)
#             pdf.rotate(45, x=None, y=None)
#             pdf.text(30, 150, "DELIVERED")
#             pdf.rotate(0)
#             pdf.set_text_color(0, 0, 0)  # Reset to normal

#         # --- Add logo if available ---
#         logo_url = tenant_design.get("logo_url", "")
#         if logo_url:
#             try:
#                 if logo_url.startswith("http"):
#                     response = requests.get(logo_url, timeout=5)
#                     if response.status_code == 200:
#                         pdf.image(BytesIO(response.content), x=10, y=8, w=25)
#                 else:
#                     logo_path = os.path.join(os.getcwd(), logo_url.lstrip("/"))
#                     if os.path.exists(logo_path):
#                         pdf.image(logo_path, x=10, y=8, w=25)
#             except Exception as e:
#                 print(f"⚠️ Failed to load logo: {e}")

#         # --- Header text beside logo ---
#         pdf.set_xy(40, 10)
#         pdf.set_font("Arial", "B", 16)
#         pdf.set_text_color(r, g, b)
#         pdf.cell(0, 8, tenant_design.get("company_name",""), ln=True)
#         pdf.set_font("Arial", "", 12)
#         pdf.set_text_color(0, 0, 0)
#         pdf.cell(0, 8, tenant_design.get("tagline",""), ln=True)
#         pdf.set_font("Arial", "", 10)
#         pdf.cell(0, 6, tenant_design.get("company_address", ""), ln=True)
#         pdf.cell(0, 6, tenant_design.get("company_phone", ""), ln=True)
#         pdf.ln(15)

#         # --- Divider ---
#         pdf.set_draw_color(200, 200, 200)
#         pdf.line(10, pdf.get_y(), 200, pdf.get_y())
#         pdf.ln(8)

#         # --- Customer Info ---
#         pdf.set_font("Arial", "B", 12)
#         pdf.set_text_color(r, g, b)
#         pdf.cell(200, 8, "Customer Details:", ln=True)
#         pdf.set_text_color(0, 0, 0)
#         pdf.set_font("Arial", "", 11)
#         pdf.cell(200, 8, f"Customer Name: {data.get('customer_name', '-')}", ln=True)
#         pdf.cell(200, 8, f"Email: {data.get('email', '-')}", ln=True)
#         pdf.cell(200, 8, f"Contact Number: {data.get('contact_number', '-')}", ln=True)
#         pdf.cell(200, 8, f"City: {data.get('city', '-')}", ln=True)
#         pdf.cell(200, 8, f"Serial Number: {data.get('serial_number', '-')}", ln=True)
#         pdf.ln(5)

#         # --- Problem ---
#         pdf.set_font("Arial", "B", 12)
#         pdf.set_text_color(r, g, b)
#         pdf.cell(200, 8, "Problem:", ln=True)
#         pdf.set_text_color(0, 0, 0)
#         pdf.set_font("Arial", "", 11)
#         pdf.multi_cell(0, 8, data.get("problem", "N/A"))
#         pdf.ln(5)

#         # --- Accessories ---
#         pdf.set_font("Arial", "B", 12)
#         pdf.set_text_color(r, g, b)
#         pdf.cell(200, 8, "Accessories:", ln=True)
#         pdf.set_text_color(0, 0, 0)
#         pdf.set_font("Arial", "", 11)
#         acc = ", ".join(data.get("accessories", [])) if data.get("accessories") else "-"
#         pdf.multi_cell(0, 8, acc)
#         pdf.ln(5)

#         # --- Warranty & Dispatch ---
#         pdf.cell(200, 8, f"Warranty: {data.get('warranty', '-')}", ln=True)
#         pdf.cell(200, 8, f"Dispatch Through: {data.get('dispatch_through', '-')}", ln=True)
#         pdf.ln(5)

#         # --- Items Table ---
#         pdf.set_font("Arial", "B", 12)
#         pdf.set_text_color(r, g, b)
#         pdf.cell(200, 8, "Items:", ln=True)
#         pdf.set_text_color(0, 0, 0)
#         pdf.set_font("Arial", "", 11)
#         items = data.get("items", [])
#         if not items:
#             pdf.cell(200, 8, "No items listed.", ln=True)
#         else:
#             for idx, item in enumerate(items, start=1):
#                 pdf.cell(
#                     200,
#                     8,
#                     f"{idx}. {item.get('description', '')} (Qty: {item.get('quantity', 1)})",
#                     ln=True,
#                 )

#         pdf.ln(10)

#         # --- Footer ---
#         pdf.set_font("Arial", "I", 10)
#         pdf.set_text_color(80, 80, 80)
#         pdf.multi_cell(0, 8, tenant_design.get("footer_note", "Thank you for your business!"))

#         # --- Save PDF ---
#         pdf.output(file_path)
#         print(f"✅ PDF generated: {file_path}")

#         return relative_url

#     except Exception as e:
#         print("❌ PDF generation error:", e)
#         return None

import os
import json
import pdfkit
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

def generate_pdf(data, tenant_design):
    """
    Generate a professional HTML-based PDF (challan_preview.html)
    Includes accessories, theme color, fonts, and images.
    """
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        templates_dir = os.path.join(base_dir, "templates")
        static_dir = os.path.join(base_dir, "..", "static", "pdfs")
        os.makedirs(static_dir, exist_ok=True)

        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template("challan_template.html")

        challan_no = data.get("challan_no", f"CH-{datetime.now().strftime('%d%m%Y%H%M%S')}")
        pdf_filename = f"{challan_no}.pdf"
        pdf_path = os.path.join(static_dir, pdf_filename)
        relative_url = f"/static/pdfs/{pdf_filename}"

        # ✅ Format accessories
        accessories_list = data.get("accessories", [])
        if isinstance(accessories_list, str):
            try:
                accessories_list = json.loads(accessories_list)
            except Exception:
                accessories_list = [accessories_list]
        if not isinstance(accessories_list, list):
            accessories_list = [str(accessories_list)]
        accessories_str = ", ".join(accessories_list) if accessories_list else "—"

        # ✅ Fix logo path
        logo_url = tenant_design.get("logo_url", "")
        if logo_url and not logo_url.startswith("http"):
            logo_url = f"{baselocation_url}{logo_url}"

        # ✅ Fix images
        image_urls = []
        for img in data.get("images", []):
            if img and not str(img).startswith("http"):
                image_urls.append(f"{baselocation_url}/{img.lstrip('/')}")
            else:
                image_urls.append(img)

        html_content = template.render(
                tenant_design=tenant_design,
                data=data,
                accessories=accessories_str,
                images=image_urls,
                logo_url=logo_url,
                terms_conditions=tenant_design.get("terms_conditions", ""),   # ✅ Added line
                is_delivered=(data.get("status", "").lower() == "delivered"),
                generated_on=datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
            )


        pdfkit.from_string(
            html_content,
            pdf_path,
            options={
                "enable-local-file-access": "",
                "quiet": "",
                "margin-top": "10mm",
                "margin-bottom": "10mm",
                "margin-left": "10mm",
                "margin-right": "10mm",
                "encoding": "UTF-8",
            },
        )

        print(f"✅ PDF generated successfully: {pdf_path}")
        return relative_url

    except Exception as e:
        print("❌ Error generating styled PDF:", e)
        return None
