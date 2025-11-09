# routes/admin/__init__.py
from flask import Blueprint

from .admin_auth import admin_auth_bp
from .tenants import tenants_bp
from .tenant_users import tenant_users_bp
from .subscriptions import subscriptions_bp
from .logs import logs_bp

admin_bp = Blueprint("admin", __name__)
admin_bp.register_blueprint(admin_auth_bp)
admin_bp.register_blueprint(tenants_bp)
admin_bp.register_blueprint(tenant_users_bp)
admin_bp.register_blueprint(subscriptions_bp)
admin_bp.register_blueprint(logs_bp)
