# import psycopg2, os

# DB_CONFIG = {
#     "dbname": os.environ.get("DB_NAME", "Challan_maker_enterprise"),
#     "user": os.environ.get("DB_USER", "postgres"),
#     "password": os.environ.get("DB_PASS", "AutomanSolutions"),
#     "host": os.environ.get("DB_HOST", "localhost"),
#     "port": os.environ.get("DB_PORT", "5432"),
# }

# def get_db_connection():
#     return psycopg2.connect(**DB_CONFIG)



import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Neon connection URL (full URL with SSL)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_sCUp8re2NYbR@ep-proud-brook-a4h4pqu0-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"
)

def get_db_connection():
    """
    Create and return a secure PostgreSQL connection using Neon URL.
    SSL is enforced as Neon requires it.
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("✅ Connected to Neon PostgreSQL successfully.")
        return conn
    except Exception as e:
        print("❌ Database connection failed:", str(e))
        raise e


