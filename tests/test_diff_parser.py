from pr_sentinel.core.diff_parser import DiffParser
from pr_sentinel.core.models import ChangeType

SAMPLE_DIFF = """diff --git a/src/calculator.py b/src/calculator.py
index 1234567..89abcdef 100644
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -1,5 +1,6 @@
 def add(a, b):
-    return a - b
+    # Fixed addition bug
+    return a + b
 
 def subtract(a, b):
     return a - b
"""


def test_parse_diff_files_and_hunks():
    ctx = DiffParser.parse_diff(SAMPLE_DIFF, branch_name="fix-add", pr_title="Fix Calculator Addition")

    assert len(ctx.files) == 1
    file_diff = ctx.files[0]
    assert file_diff.target_file == "src/calculator.py"
    assert file_diff.change_type == ChangeType.MODIFIED
    assert len(file_diff.hunks) == 1
    assert ctx.total_added >= 1
    assert ctx.total_deleted >= 1
    assert ctx.branch_name == "fix-add"


def test_parse_empty_diff():
    ctx = DiffParser.parse_diff("")
    assert len(ctx.files) == 0
    assert ctx.total_added == 0
    assert ctx.total_deleted == 0
