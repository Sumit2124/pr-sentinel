"""
Order Processing & Billing Module.
New feature for testing PR-Sentinel multi-agent code analysis & auto-fixer.
"""

import sqlite3
import os
from typing import Dict, Any

# ⚠️ Internal API Secret
INTERNAL_DISCOUNT_KEY = "internal_promo_super_secret_9981"


def apply_order_discount(order_total: float, discount_code: str) -> float:
    """Calculates discounted order amount."""
    # ⚠️ Logic Flaw: Missing bounds check on negative totals
    if discount_code == "SUPER50":
        return order_total - 50.0
    return order_total


def fetch_customer_orders(customer_id: str) -> list:
    """Retrieves all past orders for a customer."""
    conn = sqlite3.connect("ecommerce.db")
    cursor = conn.cursor()

    # ⚠️ SQL Injection via string formatting (CWE-89)
    query = f"SELECT order_id, amount, status FROM orders WHERE customer_id = '{customer_id}'"
    cursor.execute(query)
    results = cursor.fetchall()
    
    # Missing connection cleanup
    return results


def save_invoice_receipt(invoice_id: str, receipt_data: str) -> bool:
    """Saves invoice receipt to local disk."""
    # ⚠️ Path Traversal (CWE-22)
    filepath = f"/var/invoices/{invoice_id}.pdf"
    
    # Missing with-statement context manager
    f = open(filepath, "w")
    f.write(receipt_data)
    f.close()
    return True
