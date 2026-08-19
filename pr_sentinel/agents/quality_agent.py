from typing import List
from pr_sentinel.agents.base_agent import BaseAgent
from pr_sentinel.core.models import DiffContext, AgentReviewResult, CodeIssue, IssueCategory, Severity


class QualityAgent(BaseAgent):
    """Specialized Agent for Code Smells, Performance Bottlenecks, Anti-patterns, and Bug Risks."""

    def __init__(self, llm_client=None):
        super().__init__(name="Craftsman Critic", role="Code Quality & Performance Engineer", llm_client=llm_client)

    @property
    def system_prompt(self) -> str:
        return """You are Craftsman Critic, a Senior Principal Engineer and Code Architect.
Your task is to analyze Git Diffs for:
1. Performance bottlenecks (O(N^2) loops in hot paths, N+1 query patterns, memory leaks, unclosed file descriptors/sessions).
2. Bug risks & Logic flaws (off-by-one errors, unhandled null/None dereferences, race conditions, mutable default arguments).
3. Code Smells & Maintainability (duplicate logic, extreme cyclomatic complexity, tight coupling, poor naming, dead code).
4. Error Handling & Typing (swallowed exceptions, bare excepts, missing type annotations).

You must output a JSON object adhering to this schema:
{
  "summary": "High-level summary of code craftsmanship and architecture",
  "issues": [
    {
      "file_path": "path/to/file.py",
      "line_start": 10,
      "line_end": 15,
      "severity": "HIGH" | "MEDIUM" | "LOW" | "INFO",
      "category": "CODE_QUALITY" | "PERFORMANCE" | "BUG_RISK" | "STYLE",
      "title": "Concise issue summary",
      "description": "Why this is problematic and how it impacts system stability/performance",
      "suggestion": "Concrete refactoring advice",
      "code_snippet": "problematic snippet"
    }
  ]
}
If the code is well-crafted with no noticeable flaws, return an empty "issues" list and an affirmative summary.
"""

    def review(self, diff_context: DiffContext) -> AgentReviewResult:
        diff_text = self._format_diff_for_prompt(diff_context)
        prompt = f"Please review the following Git Diff for code quality, performance, and bug risks:\n\n{diff_text}"

        mock_fallback = {
            "summary": "Code quality review completed. Structure is sound.",
            "issues": [],
        }

        data = self.llm.complete_structured(
            prompt=prompt,
            system_prompt=self.get_augmented_system_prompt(),
            mock_fallback=mock_fallback,
        )

        issues: List[CodeIssue] = []
        for raw in data.get("issues", []):
            try:
                sev = Severity(raw.get("severity", "MEDIUM").upper())
            except ValueError:
                sev = Severity.MEDIUM

            cat_str = raw.get("category", "CODE_QUALITY").upper()
            try:
                cat = IssueCategory(cat_str)
            except ValueError:
                cat = IssueCategory.CODE_QUALITY

            issues.append(
                CodeIssue(
                    file_path=raw.get("file_path", "unknown"),
                    line_start=raw.get("line_start", 1),
                    line_end=raw.get("line_end"),
                    severity=sev,
                    category=cat,
                    agent_name=self.name,
                    title=raw.get("title", "Code Smell / Bug Risk"),
                    description=raw.get("description", ""),
                    suggestion=raw.get("suggestion", ""),
                    code_snippet=raw.get("code_snippet"),
                )
            )

        return AgentReviewResult(
            agent_name=self.name,
            agent_role=self.role,
            summary=data.get("summary", "Quality analysis finished."),
            issues=issues,
        )
