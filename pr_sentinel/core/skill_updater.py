import os
from typing import Dict, Any, Optional
from pr_sentinel.core.models import PRReviewReport, DiffContext
from pr_sentinel.llm.client import LLMClient


class SkillUpdater:
    """Refactors and evolves AI Agent Skill files (SKILL.md) based on resolved PR review feedback and codebase lessons."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    @property
    def system_prompt(self) -> str:
        return """You are the AI Skill Architect & Continuous Learning Engine.
Your job is to take an existing AI Agent Skill definition (SKILL.md) and update it based on newly resolved code review comments, security findings, and applied patches.

Guidelines for Updating SKILL.md:
1. Preserve the existing skill structure, frontmatter (if any), and core objectives.
2. Add new defensive coding rules, verification checklists, and anti-patterns derived from the resolved issues.
3. Update code examples with the positive patterns that resolved the PR findings.
4. Ensure instructions are clear, concise, actionable, and prevent AI agents from repeating past mistakes.

You must output a JSON object:
{
  "summary_of_changes": "Bullet points describing what guidelines and rules were added/refined in the skill",
  "updated_skill_content": "# Updated SKILL.md content in markdown format...",
  "efficiency_gain_notes": "Explanation of how this updated skill improves AI agent efficiency and accuracy"
}
"""

    def update_skill_from_report(
        self,
        skill_content: str,
        report: PRReviewReport,
        diff_context: Optional[DiffContext] = None,
    ) -> Dict[str, Any]:
        """Evolves the skill file using the findings and patches from the review report."""
        if not skill_content.strip():
            skill_content = "# AI Coding Skill\n\n## Guidelines\n- Write clean, modular, tested code."

        issues_summary = []
        for i, iss in enumerate(report.issues, 1):
            issues_summary.append(
                f"- Issue #{i}: [{iss.severity.value}] {iss.title} ({iss.file_path})\n"
                f"  Problem: {iss.description}\n"
                f"  Resolution Applied: {iss.suggestion}\n"
            )

        patches_summary = []
        for p in report.patches:
            patches_summary.append(f"Applied Patch for {p.file_path}:\n{p.unified_diff}\n")

        prompt = (
            f"Here is the Current SKILL.md content:\n```markdown\n{skill_content}\n```\n\n"
            f"Here are the Resolved Review Issues from the PR:\n{''.join(issues_summary) or 'No major issues.'}\n\n"
            f"Here are the Applied Patches & Golden Solutions:\n{''.join(patches_summary) or 'No patches.'}\n\n"
            f"Please update and evolve the SKILL.md so future AI agents follow these lessons and avoid repeating these flaws."
        )

        mock_fallback = {
            "summary_of_changes": "Added defensive coding guidelines and verification rules based on resolved PR.",
            "updated_skill_content": skill_content + "\n\n## 🛡️ Learned Quality Guardrails\n- Strictly validate input parameters and avoid raw string interpolation.",
            "efficiency_gain_notes": "Prevents downstream coding agents from introducing security vulnerabilities.",
        }

        return self.llm.complete_structured(
            prompt=prompt,
            system_prompt=self.system_prompt,
            mock_fallback=mock_fallback,
        )
