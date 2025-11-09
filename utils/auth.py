import os
import jwt
import bcrypt
from functools import wraps
from flask import request, jsonify
from datetime import datetime, timedelta

# ============================================================
# 🔹 CONFIGURATION
# ============================================================
ADMIN_SECRET = os.getenv("ADMIN_JWT_SECRET", "automan_admin_secret")
TENANT_SECRET = os.getenv("TENANT_JWT_SECRET", "tenant_secret_key")
JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", 8))

# Optional shared blacklist for logout functionality
try:
    from routes.admin.admin_auth import TOKEN_BLACKLIST
except ImportError:
    TOKEN_BLACKLIST = set()

# ============================================================
# 🔹 TOKEN GENERATION & VALIDATION
# ============================================================
def generate_token(payload: dict, is_admin: bool = False) -> str:
    """
    Generates a JWT token. Uses admin or tenant secret accordingly.
    """
    payload["exp"] = datetime.utcnow() + timedelta(hours=JWT_EXP_HOURS)
    secret = ADMIN_SECRET if is_admin else TENANT_SECRET
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, is_admin: bool = False) -> dict:
    """
    Decodes JWT token, verifies signature and expiry.
    """
    secret = ADMIN_SECRET if is_admin else TENANT_SECRET
    return jwt.decode(token, secret, algorithms=["HS256"])

# ============================================================
# 🔹 PASSWORD HASHING UTILITIES (BCRYPT)
# ============================================================
def hash_password(password: str) -> str:
    """
    Hashes a plaintext password using bcrypt.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifies a password against its bcrypt hash.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

# ============================================================
# 🔹 ADMIN AUTH DECORATOR
# ============================================================
def admin_token_required(f):
    """
    Decorator to protect admin routes with JWT verification and blacklist check.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ")[1]
        if token in TOKEN_BLACKLIST:
            return jsonify({"error": "Session expired or logged out"}), 401

        try:
            decoded = decode_token(token, is_admin=True)
            request.admin = decoded
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return decorated

# ============================================================
# 🔹 TENANT AUTH DECORATOR
# ============================================================
def tenant_token_required(f):
    """
    Decorator to protect tenant routes with JWT verification.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ")[1]
        try:
            decoded = decode_token(token, is_admin=False)
            request.tenant = decoded
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return decorated
