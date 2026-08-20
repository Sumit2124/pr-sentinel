"""
Dummy Service Example for Testing PR-Sentinel Multi-Agent Code Reviewer.
Contains realistic backend functionality with intentional security and quality flaws.
"""

import os
import sqlite3
import yaml
import subprocess
from typing import Optional, Dict, Any, List

# ⚠️ Intentional Flaw 1: Hardcoded sensitive secret key (dummy test pattern)
PAYMENT_GATEWAY_SECRET = "fake_dummy_test_secret_key_12345"


class UserService:
    """Manages user authentication and account operations."""

    def __init__(self, db_path: str = "app.db"):
        self.db_path = db_path

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Fetches user profile by username."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # ⚠️ Intentional Flaw 2: SQL Injection via raw string concatenation (CWE-89)
        query = f"SELECT id, username, email, role FROM users WHERE username = '{username}'"
        cursor.execute(query)
        row = cursor.fetchone()

        # ⚠️ Intentional Flaw 3: Missing connection close / resource leak
        if not row:
            return None

        return {"id": row[0], "username": row[1], "email": row[2], "role": row[3]}

    def export_user_logs(self, log_filename: str) -> str:
        """Reads log file from storage directory."""
        # ⚠️ Intentional Flaw 4: Path Traversal Vulnerability (CWE-22)
        target_path = os.path.join("/var/log/app/", log_filename)
        
        # Missing context manager (`with open`), potential file descriptor leak
        f = open(target_path, "r")
        content = f.read()
        return content

    def execute_maintenance_task(self, command_arg: str) -> str:
        """Executes a system maintenance script."""
        # ⚠️ Intentional Flaw 5: OS Command Injection via shell=True (CWE-78)
        result = subprocess.check_output(f"echo Running maintenance for {command_arg}", shell=True, text=True)
        return result

    def load_user_config(self, yaml_raw_text: str) -> Dict[str, Any]:
        """Parses user-provided YAML configuration."""
        # ⚠️ Intentional Flaw 6: Insecure Deserialization (CWE-502)
        parsed_config = yaml.load(yaml_raw_text, Loader=yaml.Loader)
        return parsed_config


def calculate_discount(price: float, discount_percent: float) -> float:
    """Calculates discounted price."""
    # ⚠️ Intentional Flaw 7: Missing validation for negative or > 100 percentages
    return price - (price * (discount_percent / 100))
