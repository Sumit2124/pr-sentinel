from typing import List
from pr_sentinel.agents.base_agent import BaseAgent
from pr_sentinel.core.models import DiffContext, AgentReviewResult, CodeIssue, GeneratedTest, IssueCategory, Severity


class TestAgent(BaseAgent):
    """Specialized Agent for Test Coverage Analysis, Missing Edge Cases, and Regression Test Generation."""

    def __init__(self, llm_client=None):
        super().__init__(name="QA Sentinel", role="Test Coverage & Regression Specialist", llm_client=llm_client)

    @property
    def system_prompt(self) -> str:
        return """You are QA Sentinel, a Lead QA Automation Engineer.
Your task is to analyze Git Diffs to detect:
1. Missing unit tests or integration tests for newly introduced logic/endpoints/functions.
2. Unhandled edge cases (e.g. empty inputs, null bytes, negative values, timeout conditions, network failures).
3. Test regressions or deleted tests that reduce coverage.

You must output a JSON object adhering to this schema:
{
  "summary": "High-level summary of test readiness and test gap analysis",
  "issues": [
    {
      "file_path": "path/to/file.py",
      "line_start": 1,
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "title": "Missing test case for ...",
      "description": "Specific scenario or edge case not covered by tests",
      "suggestion": "How to test this properly"
    }
  ],
  "suggested_tests": [
    {
      "target_file": "path/to/file.py",
      "test_file_path": "tests/test_file.py",
      "framework": "pytest",
      "test_code": "def test_edge_case():\\n    ...",
      "description": "Tests edge case where input is None",
      "covers_issue_title": "Missing test case for ..."
    }
  ]
}
"""

    def review(self, diff_context: DiffContext) -> AgentReviewResult:
        diff_text = self._format_diff_for_prompt(diff_context)
        prompt = f"Please analyze test coverage and generate regression test cases for this Git Diff:\n\n{diff_text}"

        mock_fallback = {
            "summary": "Test coverage assessment completed.",
            "issues": [],
            "suggested_tests": [],
        }

        data = self.llm.complete_structured(
            prompt=prompt,
            system_prompt=self.system_prompt,
            mock_fallback=mock_fallback,
        )

        issues: List[CodeIssue] = []
        for raw in data.get("issues", []):
            try:
                sev = Severity(raw.get("severity", "LOW").upper())
            except ValueError:
                sev = Severity.LOW

            issues.append(
                CodeIssue(
                    file_path=raw.get("file_path", "unknown"),
                    line_start=raw.get("line_start", 1),
                    severity=sev,
                    category=IssueCategory.TEST_COVERAGE,
                    agent_name=self.name,
                    title=raw.get("title", "Missing Test Coverage"),
                    description=raw.get("description", ""),
                    suggestion=raw.get("suggestion", ""),
                )
            )

        tests: List[GeneratedTest] = []
        for raw_t in data.get("suggested_tests", []):
            tests.append(
                GeneratedTest(
                    target_file=raw_t.get("target_file", "unknown"),
                    test_file_path=raw_t.get("test_file_path", "tests/test_auto.py"),
                    framework=raw_t.get("framework", "pytest"),
                    test_code=raw_t.get("test_code", "# Test code"),
                    description=raw_t.get("description", "Automated regression test"),
                    covers_issue_title=raw_t.get("covers_issue_title"),
                )
            )

        return AgentReviewResult(
            agent_name=self.name,
            agent_role=self.role,
            summary=data.get("summary", "Test analysis finished."),
            issues=issues,
            generated_tests=tests,
        )
