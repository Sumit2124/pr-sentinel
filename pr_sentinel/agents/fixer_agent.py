from typing import List, Dict, Any
from pr_sentinel.agents.base_agent import BaseAgent
from pr_sentinel.core.models import DiffContext, AgentReviewResult, SuggestedPatch, CodeIssue


class FixerAgent(BaseAgent):
    """Specialized Agent that generates valid Git Patch diffs to automatically resolve identified issues."""

    def __init__(self, llm_client=None):
        super().__init__(name="Patch Surgeon", role="Automated Patch & Refactoring Synthesizer", llm_client=llm_client)

    @property
    def system_prompt(self) -> str:
        return """You are Patch Surgeon, an expert code refactorer and patch synthesizer.
Your task is to take a set of identified code issues and generate concrete, minimal, working unified diff patches that fix them.

Rules for Patches:
1. Fix ONLY the targeted issue. Do not make unrelated aesthetic changes.
2. Ensure the fixed code compiles/runs cleanly and does not introduce regressions.
3. Output the exact unified diff format compatible with `git apply`.

You must output a JSON object adhering to this schema:
{
  "summary": "Summary of generated fixes",
  "patches": [
    {
      "file_path": "path/to/file.py",
      "line_start": 20,
      "line_end": 25,
      "original_code": "def query_user(name):\\n    cursor.execute(f'SELECT * FROM users WHERE name = {name}')",
      "fixed_code": "def query_user(name):\\n    cursor.execute('SELECT * FROM users WHERE name = %s', (name,))",
      "unified_diff": "--- a/path/to/file.py\\n+++ b/path/to/file.py\\n@@ -20,2 +20,2 @@\\n-def query_user(name):\\n-    cursor.execute(f'SELECT * FROM users WHERE name = {name}')\\n+def query_user(name):\\n+    cursor.execute('SELECT * FROM users WHERE name = %s', (name,))",
      "rationale": "Replaced dangerous string interpolation with parameterized SQL query to prevent SQL Injection.",
      "confidence_score": 0.95
    }
  ]
}
"""

    def synthesize_fixes(self, diff_context: DiffContext, issues: List[CodeIssue]) -> List[SuggestedPatch]:
        """Generates patches targeting the given issues."""
        if not issues:
            return []

        diff_text = self._format_diff_for_prompt(diff_context)
        
        issue_summaries = []
        for idx, iss in enumerate(issues, 1):
            issue_summaries.append(
                f"{idx}. [{iss.severity.value}] {iss.title} at {iss.file_path}:{iss.line_start}\n"
                f"   Problem: {iss.description}\n"
                f"   Suggestion: {iss.suggestion}\n"
            )

        prompt = (
            f"Here is the PR Diff:\n{diff_text}\n\n"
            f"Here are the issues flagged by other reviewer agents:\n"
            f"{''.join(issue_summaries)}\n\n"
            f"Please generate unified patch fixes for these issues."
        )

        mock_fallback = {
            "summary": "No patches generated.",
            "patches": [],
        }

        data = self.llm.complete_structured(
            prompt=prompt,
            system_prompt=self.get_augmented_system_prompt(),
            mock_fallback=mock_fallback,
        )

        patches: List[SuggestedPatch] = []
        from pr_sentinel.core.reflection_engine import mistake_memory

        for raw in data.get("patches", []):
            fpath = raw.get("file_path", "unknown")
            udiff = raw.get("unified_diff", "")

            # Patch Self-Validation & Syntax Repair
            if udiff and not udiff.startswith("--- "):
                if not fpath in udiff and fpath != "unknown":
                    udiff = f"--- a/{fpath}\n+++ b/{fpath}\n" + udiff
                # Record the syntax mistake to memory to avoid repeating
                mistake_memory.record_mistake(
                    category="MALFORMED_PATCH",
                    agent_name=self.name,
                    description="Generated patch without standard '--- a/' and '+++ b/' unified headers",
                    flawed_approach=f"❌ Outputting diff snippet for '{fpath}' without headers: `{udiff[:60]}...`",
                    positive_exemplar=f"✅ Wrap with valid headers:\n```diff\n--- a/{fpath}\n+++ b/{fpath}\n{udiff}\n```",
                    corrective_rule="Always prepend unified diff headers '--- a/<filepath>' and '+++ b/<filepath>' with valid line hunks.",
                )

            patches.append(
                SuggestedPatch(
                    file_path=fpath,
                    line_start=raw.get("line_start", 1),
                    line_end=raw.get("line_end", 1),
                    original_code=raw.get("original_code", ""),
                    fixed_code=raw.get("fixed_code", ""),
                    unified_diff=udiff,
                    rationale=raw.get("rationale", "Automated bug fix"),
                    confidence_score=float(raw.get("confidence_score", 0.9)),
                )
            )

        return patches

    def review(self, diff_context: DiffContext) -> AgentReviewResult:
        # Standalone invocation without prior issues
        return AgentReviewResult(
            agent_name=self.name,
            agent_role=self.role,
            summary="Patch Surgeon stands ready to generate fixes for detected issues.",
            patches=[],
        )
