# subscriptions.py
from flask import Blueprint, request, jsonify
from utils.db import get_db_connection
from utils.auth import admin_token_required
import json
from datetime import datetime

subscriptions_bp = Blueprint("subscriptions", __name__, url_prefix="/admin/subscriptions")


@subscriptions_bp.route("/<int:tenant_id>", methods=["GET"])
@admin_token_required
def list_subscriptions(tenant_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, tenant_id, plan_name, price, start_date, end_date, is_active FROM subscriptions WHERE tenant_id=%s ORDER BY start_date DESC", (tenant_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"subscriptions": rows}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@subscriptions_bp.route("/subscriptions/<int:tenant_id>", methods=["POST"])
@admin_token_required
def create_subscription(tenant_id):
    body = request.get_json() or {}
    plan_name = body.get("plan_name")
    price = body.get("price")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    is_active = bool(body.get("is_active", True))

    if not plan_name or not start_date or not end_date:
        return jsonify({"error": "plan_name, start_date and end_date required"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO subscriptions (tenant_id, plan_name, price, start_date, end_date, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, plan_name, price, start_date, end_date, is_active
        """, (tenant_id, plan_name, price, start_date, end_date, is_active))
        new = cur.fetchone()

        # Update tenants table subscription dates & plan
        cur.execute("UPDATE tenants SET plan=%s, subscription_start=%s, subscription_end=%s WHERE id=%s", (plan_name, start_date, end_date, tenant_id))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"subscription": new}), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 500


@subscriptions_bp.route("/subscriptions/<int:tenant_id>/<int:sub_id>", methods=["PUT"])
@admin_token_required
def update_subscription(tenant_id, sub_id):
    body = request.get_json() or {}
    plan_name = body.get("plan_name")
    price = body.get("price")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    is_active = body.get("is_active")

    updates = []
    params = []
    if plan_name is not None:
        updates.append("plan_name=%s"); params.append(plan_name)
    if price is not None:
        updates.append("price=%s"); params.append(price)
    if start_date is not None:
        updates.append("start_date=%s"); params.append(start_date)
    if end_date is not None:
        updates.append("end_date=%s"); params.append(end_date)
    if is_active is not None:
        updates.append("is_active=%s"); params.append(bool(is_active))

    if not updates:
        return jsonify({"message": "No fields to update"}), 200

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        params.extend([tenant_id, sub_id])
        sql = f"UPDATE subscriptions SET {', '.join(updates)} WHERE tenant_id=%s AND id=%s RETURNING id, tenant_id, plan_name, price, start_date, end_date, is_active"
        cur.execute(sql, tuple(params))
        updated = cur.fetchone()

        # Optionally update tenant's main subscription data
        if start_date or end_date or plan_name:
            cur.execute("UPDATE tenants SET plan=%s, subscription_start=%s, subscription_end=%s WHERE id=%s", (plan_name or None, start_date or None, end_date or None, tenant_id))

        conn.commit()
        cur.close()
        conn.close()
        if not updated:
            return jsonify({"error": "Subscription not found"}), 404
        return jsonify({"subscription": updated}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 500


@subscriptions_bp.route("/subscriptions/<int:tenant_id>/<int:sub_id>", methods=["DELETE"])
@admin_token_required
def delete_subscription(tenant_id, sub_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM subscriptions WHERE tenant_id=%s AND id=%s RETURNING id", (tenant_id, sub_id))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not deleted:
            return jsonify({"error": "Subscription not found"}), 404
        return jsonify({"message": "Subscription deleted"}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 500


@subscriptions_bp.route("/subscriptions", methods=["GET"])
@admin_token_required
def get_subscriptions():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, tenant_id, plan_name, price, start_date, end_date, is_active
            FROM subscriptions
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        subs = [
            {
                "id": r[0],
                "tenant_id": r[1],
                "plan_name": r[2],
                "price": r[3],
                "start_date": r[4].strftime("%Y-%m-%d"),
                "end_date": r[5].strftime("%Y-%m-%d"),
                "is_active": r[6],
            }
            for r in rows
        ]
        return jsonify(subs), 200
    except Exception as e:
        print("❌ Error fetching subscriptions:", e)
        return jsonify({"error": "Failed to fetch subscriptions"}), 500
