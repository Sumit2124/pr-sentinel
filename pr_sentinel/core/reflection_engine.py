import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

MISTAKE_MEMORY_FILE = os.path.expanduser(".pr_sentinel_memory.json")


class MistakeRecord(BaseModel):
    id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    category: str  # e.g., "FALSE_POSITIVE", "MALFORMED_PATCH", "HALLUCINATED_LINE", "MISSED_VULNERABILITY"
    agent_name: str
    description: str
    flawed_approach: str  # ❌ Negative: What the agent did wrong (Bad Behavior)
    positive_exemplar: str  # ✅ Positive: How to handle it correctly (Good Behavior / Golden Standard)
    corrective_rule: str  # 💡 The Generalized Rule of Thumb
    file_type: Optional[str] = None


class ReflectionEngine:
    """Stores past evaluation mistakes and transforms them into (Negative -> Positive) Few-Shot Exemplars."""

    def __init__(self, memory_path: str = MISTAKE_MEMORY_FILE):
        self.memory_path = memory_path
        self._memory: List[MistakeRecord] = self._load_memory()

    def _load_memory(self) -> List[MistakeRecord]:
        if not os.path.exists(self.memory_path):
            # Seed default high-value negative -> positive exemplars
            return self._default_seed_exemplars()
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [MistakeRecord(**m) for m in data]
        except Exception:
            return self._default_seed_exemplars()

    def _default_seed_exemplars(self) -> List[MistakeRecord]:
        """Provides initial calibrated negative -> positive few-shot exemplars."""
        return [
            MistakeRecord(
                id="seed-001",
                category="FALSE_POSITIVE",
                agent_name="SecOps Sentinel",
                description="Flagged dummy credentials in unit test fixtures as critical secret leaks.",
                flawed_approach="❌ Flagging `TEST_API_KEY = 'dummy-key-123'` inside `tests/conftest.py` as CRITICAL CWE-798.",
                positive_exemplar="✅ Check file path first. If inside `tests/` or `test_*.py`, recognize mock/dummy test values and mark as INFO or ignore.",
                corrective_rule="Distinguish mock test fixture data from actual production credentials.",
            ),
            MistakeRecord(
                id="seed-002",
                category="MALFORMED_PATCH",
                agent_name="Patch Surgeon",
                description="Generated raw code snippets instead of git-apply compatible unified diff headers.",
                flawed_approach="❌ Outputting raw Python code replacement without `--- a/file.py` and `+++ b/file.py` headers.",
                positive_exemplar="✅ Output strict Unified Diff format with valid hunk line numbers:\n```diff\n--- a/app/main.py\n+++ b/app/main.py\n@@ -10,2 +10,2 @@\n-old_code()\n+new_code()\n```",
                corrective_rule="Always wrap fixes in valid unified diff headers containing relative file paths.",
            ),
            MistakeRecord(
                id="seed-003",
                category="HALLUCINATED_SCOPE",
                agent_name="Craftsman Critic",
                description="Flagged issues in unchanged legacy lines outside the PR diff boundary.",
                flawed_approach="❌ Raising code smells on untouched legacy functions that were not modified in the PR.",
                positive_exemplar="✅ Focus review strictly on the added (`+`) or modified lines within the PR hunks.",
                corrective_rule="Limit critical issues strictly to the newly introduced PR changes, not pre-existing untouched legacy code.",
            ),
        ]

    def save_memory(self):
        try:
            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump([m.model_dump() for m in self._memory], f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save mistake memory: {e}")

    def record_mistake(
        self,
        category: str,
        agent_name: str,
        description: str,
        flawed_approach: str,
        positive_exemplar: str,
        corrective_rule: str,
        file_type: Optional[str] = None,
    ) -> MistakeRecord:
        """Records a mistake and its positive counter-example to calibrate future agent decisions."""
        import uuid
        record = MistakeRecord(
            id=str(uuid.uuid4())[:8],
            category=category,
            agent_name=agent_name,
            description=description,
            flawed_approach=flawed_approach,
            positive_exemplar=positive_exemplar,
            corrective_rule=corrective_rule,
            file_type=file_type,
        )
        self._memory.append(record)
        self.save_memory()
        return record

    def get_learned_guardrails(self, agent_name: Optional[str] = None) -> str:
        """Constructs a structured (Negative -> Positive) Few-Shot Calibration section for the LLM prompt."""
        if not self._memory:
            return ""

        relevant = [m for m in self._memory if not agent_name or m.agent_name == agent_name or m.agent_name == "ALL"]
        if not relevant:
            return ""

        lines = [
            "\n### 🎓 LEARNED CALIBRATION: PAST MISTAKES & POSITIVE TRANSFORMATION EXAMPLES:",
            "To maintain high precision and eliminate flakiness, review the following case studies of past flawed judgments and their required positive corrections:\n",
        ]

        for i, m in enumerate(relevant[-6:], 1):  # Include top 6 most relevant recent exemplars
            lines.append(f"#### Case Study {i} [{m.category} - {m.agent_name}]:")
            lines.append(f"- **The Flawed Decision to AVOID (Negative)**:\n  {m.flawed_approach}")
            lines.append(f"- **The Correct Action to TAKE (Positive)**:\n  {m.positive_exemplar}")
            lines.append(f"- **💡 Golden Principle**: {m.corrective_rule}\n")

        return "\n".join(lines)

    def list_mistakes(self) -> List[MistakeRecord]:
        return self._memory

    def clear_memory(self):
        self._memory = []
        self.save_memory()


# Global memory singleton
mistake_memory = ReflectionEngine()
