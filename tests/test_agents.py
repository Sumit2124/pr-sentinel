from pr_sentinel.core.diff_parser import DiffParser
from pr_sentinel.agents.lead_reviewer import LeadReviewerAgent
from pr_sentinel.agents.security_agent import SecurityAgent
from pr_sentinel.agents.quality_agent import QualityAgent
from pr_sentinel.agents.test_agent import TestAgent
from pr_sentinel.agents.fixer_agent import FixerAgent

SAMPLE_DIFF = """diff --git a/app/auth.py b/app/auth.py
new file mode 100644
--- /dev/null
+++ b/app/auth.py
@@ -0,0 +1,10 @@
+def check_login(user, pwd):
+    # Hardcoded bypass
+    if user == "admin" and pwd == "admin":
+        return True
+    return False
+"""


def test_agent_swarm_orchestration():
    diff_ctx = DiffParser.parse_diff(SAMPLE_DIFF, pr_title="Add Admin Auth")
    lead_agent = LeadReviewerAgent()
    report = lead_agent.review_pr(diff_ctx)

    assert report is not None
    assert report.verdict in ["APPROVE", "COMMENT", "REQUEST_CHANGES"]
    assert 0 <= report.risk_score <= 100
    assert len(report.agent_results) == 3


def test_specialized_agents_standalone():
    diff_ctx = DiffParser.parse_diff(SAMPLE_DIFF)
    sec_agent = SecurityAgent()
    qual_agent = QualityAgent()
    test_agent = TestAgent()
    fixer_agent = FixerAgent()

    s_res = sec_agent.review(diff_ctx)
    assert s_res.agent_name == "SecOps Sentinel"

    q_res = qual_agent.review(diff_ctx)
    assert q_res.agent_name == "Craftsman Critic"

    t_res = test_agent.review(diff_ctx)
    assert t_res.agent_name == "QA Sentinel"

    f_res = fixer_agent.review(diff_ctx)
    assert f_res.agent_name == "Patch Surgeon"
