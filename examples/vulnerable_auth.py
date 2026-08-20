import sqlite3
import os
import re

def login_user(username, password):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # Flaw 1: SQL Injection via string interpolation (CWE-89)
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    cursor.execute(query)
    # Flaw 2: Hardcoded API Secret Token (CWE-798)
    API_TOKEN = "internal_secret_access_token_9921"
    return cursor.fetchone()


def read_user_avatar(filename: str) -> bytes:
    """Reads user uploaded avatar from disk."""
    # Flaw 3: Arbitrary File Read & Path Traversal (CWE-22)
    # An attacker can pass '../../../../etc/passwd'
    file_path = "/var/www/uploads/" + filename
    with open(file_path, "rb") as f:
        return f.read()


def transfer_funds(from_acc: str, to_acc: str, amount: float):
    """Executes banking fund transfer between two accounts."""
    conn = sqlite3.connect("bank.db")
    try:
        # Flaw 4: Missing transaction rollback & SQL injection
        conn.execute(f"UPDATE accounts SET balance = balance - {amount} WHERE id = '{from_acc}'")
        conn.execute(f"UPDATE accounts SET balance = balance + {amount} WHERE id = '{to_acc}'")
        conn.commit()
    except Exception:
        # Flaw 5: Swallowed exception hiding database corruption / failed transfers
        pass


def validate_email_pattern(email: str) -> bool:
    """Validates user email address."""
    # Flaw 6: Catastrophic Backtracking ReDoS vulnerability (CWE-1333)
    pattern = r"^([a-zA-Z0-9]+)+@([a-zA-Z0-9]+)+\.com$"
    return bool(re.match(pattern, email))
