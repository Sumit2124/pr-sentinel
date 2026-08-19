from typing import List, Dict, Any
from pr_sentinel.agents.base_agent import BaseAgent
from pr_sentinel.core.models import DiffContext, AgentReviewResult, CodeIssue, IssueCategory, Severity


class SecurityAgent(BaseAgent):
    """Specialized Agent for AppSec, OWASP Top 10, CWE classification, and Secret Detection."""

    def __init__(self, llm_client=None):
        super().__init__(name="SecOps Sentinel", role="Application Security Auditor", llm_client=llm_client)

    @property
    def system_prompt(self) -> str:
        return """You are SecOps Sentinel, an expert Application Security and Penetration Testing Auditor.
Your job is to inspect Git Diffs and identify security vulnerabilities, including:
1. Hardcoded secrets, API tokens, passwords, private keys.
2. Injections: SQL Injection (CWE-89), OS Command Injection (CWE-78), Code Injection/eval (CWE-94), XSS (CWE-79), SSRF (CWE-918).
3. Insecure Deserialization (e.g. pickle.loads, yaml.load without SafeLoader).
4. Path Traversal & Arbitrary File Access (CWE-22).
5. Broken Authentication & Authorization, JWT misconfigurations.
6. Memory safety or race conditions.

You must output a JSON object adhering to this schema:
{
  "summary": "High-level security evaluation of the PR",
  "issues": [
    {
      "file_path": "path/to/file.py",
      "line_start": 42,
      "line_end": 45,
      "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO",
      "cwe_id": "CWE-89",
      "title": "Concise issue title",
      "description": "Detailed explanation of the vulnerability and attack vector",
      "suggestion": "Exact recommendation to fix it safely",
      "code_snippet": "vulnerable snippet"
    }
  ]
}
If no security issues are found, return an empty "issues" list and a reassuring summary.
"""

    def review(self, diff_context: DiffContext) -> AgentReviewResult:
        diff_text = self._format_diff_for_prompt(diff_context)
        prompt = f"Please audit the following Git Diff for all security vulnerabilities and sensitive data exposure:\n\n{diff_text}"

        mock_fallback = {
            "summary": "Security audit completed. No critical vulnerabilities identified.",
            "issues": [],
        }

        data = self.llm.complete_structured(
            prompt=prompt,
            system_prompt=self.system_prompt,
            mock_fallback=mock_fallback,
        )

        issues: List[CodeIssue] = []
        for raw in data.get("issues", []):
            try:
                sev = Severity(raw.get("severity", "MEDIUM").upper())
            except ValueError:
                sev = Severity.MEDIUM

            issues.append(
                CodeIssue(
                    file_path=raw.get("file_path", "unknown"),
                    line_start=raw.get("line_start", 1),
                    line_end=raw.get("line_end"),
                    severity=sev,
                    category=IssueCategory.SECURITY,
                    agent_name=self.name,
                    title=raw.get("title", "Security Vulnerability"),
                    description=raw.get("description", ""),
                    suggestion=raw.get("suggestion", ""),
                    code_snippet=raw.get("code_snippet"),
                    cwe_id=raw.get("cwe_id"),
                )
            )

        return AgentReviewResult(
            agent_name=self.name,
            agent_role=self.role,
            summary=data.get("summary", "Security review finished."),
            issues=issues,
        )
