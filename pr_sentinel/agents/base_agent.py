from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pr_sentinel.core.models import DiffContext, AgentReviewResult, CodeIssue, SuggestedPatch, GeneratedTest
from pr_sentinel.llm.client import LLMClient


class BaseAgent(ABC):
    """Abstract base class for all specialized PR-Sentinel review agents."""

    def __init__(self, name: str, role: str, llm_client: Optional[LLMClient] = None):
        self.name = name
        self.role = role
        self.llm = llm_client or LLMClient()

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Returns the specialized system prompt for the agent."""
        pass

    def get_augmented_system_prompt(self) -> str:
        """Combines the agent's core prompt with dynamic learned rules and past mistake guardrails."""
        from pr_sentinel.core.reflection_engine import mistake_memory
        learned_rules = mistake_memory.get_learned_guardrails(agent_name=self.name)
        if learned_rules:
            return f"{self.system_prompt}\n\n{learned_rules}"
        return self.system_prompt

    @abstractmethod
    def review(self, diff_context: DiffContext) -> AgentReviewResult:
        """Executes the review over the provided diff context."""
        pass

    def _format_diff_for_prompt(self, diff_context: DiffContext) -> str:
        """Formats the diff context and file hunks into clean prompt text."""
        sections = []
        if diff_context.pr_title:
            sections.append(f"PR Title: {diff_context.pr_title}")
        if diff_context.pr_description:
            sections.append(f"PR Description: {diff_context.pr_description}")

        sections.append(f"Total Files Changed: {len(diff_context.files)}")
        sections.append(f"Total Lines Added: +{diff_context.total_added}, Deleted: -{diff_context.total_deleted}\n")
        sections.append("### Changed Files & Unified Diffs:")

        for f in diff_context.files:
            sections.append(f"\n--- File: {f.target_file} ({f.change_type.value}) ---")
            if f.raw_diff:
                sections.append(f.raw_diff)
            else:
                for h in f.hunks:
                    sections.append(f"@@ -{h.old_start},{h.old_length} +{h.new_start},{h.new_length} @@ {h.section_header}")
                    sections.extend(h.lines)

        return "\n".join(sections)
