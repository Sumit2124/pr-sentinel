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
    offending_pattern: str
    corrective_guideline: str
    file_type: Optional[str] = None


class ReflectionEngine:
    """Stores past mistakes, user corrections, and injects learned guardrails into review agents to prevent flakiness."""

    def __init__(self, memory_path: str = MISTAKE_MEMORY_FILE):
        self.memory_path = memory_path
        self._memory: List[MistakeRecord] = self._load_memory()

    def _load_memory(self) -> List[MistakeRecord]:
        if not os.path.exists(self.memory_path):
            return []
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [MistakeRecord(**m) for m in data]
        except Exception:
            return []

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
        offending_pattern: str,
        corrective_guideline: str,
        file_type: Optional[str] = None,
    ) -> MistakeRecord:
        """Records a mistake/correction to permanently prevent the agent from repeating it."""
        import uuid
        record = MistakeRecord(
            id=str(uuid.uuid4())[:8],
            category=category,
            agent_name=agent_name,
            description=description,
            offending_pattern=offending_pattern,
            corrective_guideline=corrective_guideline,
            file_type=file_type,
        )
        self._memory.append(record)
        self.save_memory()
        return record

    def get_learned_guardrails(self, agent_name: Optional[str] = None) -> str:
        """Constructs an injected prompt section containing learned lessons and past mistake guardrails."""
        if not self._memory:
            return ""

        relevant = [m for m in self._memory if not agent_name or m.agent_name == agent_name or m.agent_name == "ALL"]
        if not relevant:
            return ""

        lines = [
            "\n### 🧠 CRITICAL LEARNED RULES & PAST MISTAKES TO NEVER REPEAT:",
            "Previous evaluations made the following mistakes. You MUST strictly obey these corrective guidelines to ensure zero flakiness and high precision:",
        ]
        for i, m in enumerate(relevant[-10:], 1):  # Include top 10 most recent
            lines.append(f"{i}. [{m.category}] Rule: {m.corrective_guideline}")
            lines.append(f"   Avoid: \"{m.offending_pattern}\" (Reason: {m.description})")

        return "\n".join(lines) + "\n"

    def list_mistakes(self) -> List[MistakeRecord]:
        return self._memory

    def clear_memory(self):
        self._memory = []
        self.save_memory()


# Global memory singleton
mistake_memory = ReflectionEngine()
