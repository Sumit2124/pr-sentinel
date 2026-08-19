from pr_sentinel.core.ast_analyzer import ASTAnalyzer

SAMPLE_PY_CODE = """
import os
import sys
from datetime import datetime

class UserService:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id: int):
        return self.db.find(user_id)

def standalone_helper():
    return True
"""


def test_ast_python_symbol_extraction():
    analysis = ASTAnalyzer.analyze_file_content("test.py", SAMPLE_PY_CODE)

    assert analysis["language"] == "python"
    assert "os" in analysis["imports"]
    assert "datetime.datetime" in analysis["imports"]

    scopes = analysis["scopes"]
    names = [s["name"] for s in scopes]
    assert "UserService" in names
    assert "get_user" in names
    assert "standalone_helper" in names


def test_find_enclosing_scope():
    analysis = ASTAnalyzer.analyze_file_content("test.py", SAMPLE_PY_CODE)
    # Line 11 is inside `get_user`
    scope_name = ASTAnalyzer.find_enclosing_scope(analysis["scopes"], 11)
    assert scope_name is not None
    assert "get_user" in scope_name
