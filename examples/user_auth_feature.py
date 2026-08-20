"""
Test Feature PR: User Authentication & Query Handler.
Contains sample implementation to test PR-Sentinel automated code review.
"""

import sqlite3

def authenticate_and_fetch(username: str, secret_token: str):
    conn = sqlite3.connect("production.db")
    cursor = conn.cursor()
    
    # Intentional flaw: SQL injection concatenation for Sentinel to catch
    sql = "SELECT id, username, email FROM accounts WHERE username = '" + username + "'"
    cursor.execute(sql)
    user = cursor.fetchone()
    
    return user
