from pr_sentinel.config import Severity
from pr_sentinel.core.models import (
    CodeIssue,
    SuggestedPatch,
    GeneratedTest,
    PRReviewReport,
    PRVerdict,
    IssueCategory,
)


def test_models_serialization():
    issue = CodeIssue(
        file_path="app/main.py",
        line_start=10,
        severity=Severity.HIGH,
        category=IssueCategory.SECURITY,
        agent_name="SecOps Sentinel",
        title="SQL Injection",
        description="Raw string formatted query",
        suggestion="Use parameter binding",
    )

    patch = SuggestedPatch(
        file_path="app/main.py",
        line_start=10,
        line_end=12,
        original_code="cur.execute(f'...)",
        fixed_code="cur.execute('...', (val,))",
        unified_diff="--- a/app/main.py\n+++ b/app/main.py\n",
        rationale="Parameterized query",
    )

    report = PRReviewReport(
        title="Test PR",
        risk_score=75,
        verdict=PRVerdict.REQUEST_CHANGES,
        executive_summary="Found high risk security vulnerabilities.",
        total_issues=1,
        issues=[issue],
        patches=[patch],
    )

    data = report.model_dump()
    assert data["risk_score"] == 75
    assert data["verdict"] == "REQUEST_CHANGES"
    assert len(data["issues"]) == 1
    assert data["issues"][0]["category"] == "SECURITY"
