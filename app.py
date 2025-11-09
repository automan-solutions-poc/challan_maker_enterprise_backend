from flask import Flask
from flask_cors import CORS
from flask_mail import Mail

# Initialize Flask-Mail globally
mail = Mail()


def create_app():
    app = Flask(__name__)

    # ✅ CORS setup for React frontend
    from flask_cors import CORS

# ✅ CORS Configuration (for React Admin & Tenant UIs)
    CORS(
        app,
        origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000","http://localhost:3001",
            "http://127.0.0.1:3001"
        ],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With"
        ],
        supports_credentials=True,
    )


    # ✅ Default Mail Config (used if tenant email not configured)
    app.config.update({
        "MAIL_SERVER": "smtp.gmail.com",
        "MAIL_PORT": 587,
        "MAIL_USE_TLS": True,
        "MAIL_USERNAME": "yourcompanyemail@gmail.com",
        "MAIL_PASSWORD": "your_app_password",  # Gmail app password
        "MAIL_DEFAULT_SENDER": ("Phoenix Computers", "yourcompanyemail@gmail.com"),
    })

    mail.init_app(app)

    # ============================================================
    # 🔹 IMPORT & REGISTER BLUEPRINTS
    # ============================================================

    # ------------------ ADMIN ROUTES ------------------
    from routes.admin.admin_auth import admin_auth_bp
    from routes.admin.tenants import tenants_bp
    from routes.admin.tenant_users import tenant_users_bp
    from routes.admin.subscriptions import subscriptions_bp
    from routes.admin.logs import logs_bp

    # ------------------ TENANT ROUTES ------------------
    from routes.tenant import tenant_bp
    from routes.tenant.dashboard import dashboard_bp
    from routes.tenant.settings import tenant_settings_bp, upload_bp
    from routes.tenant.challans import challans_bp
    from routes.tenant.email_settings import email_settings_bp
    from routes.admin.dashboard import admin_dashboard_bp

    # ============================================================
    # ✅ REGISTER BLUEPRINTS WITH PREFIXES
    # ============================================================

    # ---------- Admin APIs ----------

# Register under admin prefix
    app.register_blueprint(admin_dashboard_bp, url_prefix="/api/admin")

    app.register_blueprint(admin_auth_bp, url_prefix="/api/admin")
    app.register_blueprint(tenants_bp, url_prefix="/api/admin")
    app.register_blueprint(tenant_users_bp, url_prefix="/api/admin/tenant_users")
    app.register_blueprint(subscriptions_bp, url_prefix="/api/admin")
    app.register_blueprint(logs_bp, url_prefix="/api/admin")

    # ---------- Tenant APIs ----------
    app.register_blueprint(tenant_bp, url_prefix="/api/tenant")
    app.register_blueprint(dashboard_bp, url_prefix="/api/tenant")
    app.register_blueprint(tenant_settings_bp, url_prefix="/api/tenant")
    app.register_blueprint(upload_bp, url_prefix="/api/tenant")
    app.register_blueprint(challans_bp, url_prefix="/api/tenant")
    app.register_blueprint(email_settings_bp, url_prefix="/api/tenant")

    # ============================================================
    # ✅ BASE ROUTE
    # ============================================================
    @app.route("/")
    def home():
        return {
            "message": "🚀 Automan Solutions API is running",
            "services": {
                "admin": "/api/admin/*",
                "tenant": "/api/tenant/*",
            },
        }

    return app


# ============================================================
# 🔹 ENTRY POINT
# ============================================================
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=6001, debug=True)
