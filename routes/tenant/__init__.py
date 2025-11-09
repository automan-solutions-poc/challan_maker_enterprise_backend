from flask import Blueprint
from .tenant_auth import tenant_auth_bp
from .challans import challans_bp
from .dashboard import dashboard_bp
from .settings import tenant_settings_bp

tenant_bp = Blueprint("tenant", __name__)
tenant_bp.register_blueprint(tenant_auth_bp)
tenant_bp.register_blueprint(challans_bp)
tenant_bp.register_blueprint(dashboard_bp)
tenant_bp.register_blueprint(tenant_settings_bp)
