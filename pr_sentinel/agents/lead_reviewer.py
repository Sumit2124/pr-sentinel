from typing import List, Optional
from pr_sentinel.agents.base_agent import BaseAgent
from pr_sentinel.agents.security_agent import SecurityAgent
from pr_sentinel.agents.quality_agent import QualityAgent
from pr_sentinel.agents.test_agent import TestAgent
from pr_sentinel.agents.fixer_agent import FixerAgent
from pr_sentinel.core.models import (
    DiffContext,
    PRReviewReport,
    PRVerdict,
    CodeIssue,
    AgentReviewResult,
    Severity,
)
from pr_sentinel.config import settings
from pr_sentinel.llm.client import LLMClient


class LeadReviewerAgent(BaseAgent):
    """Lead Orchestrator that coordinates the review swarm, synthesizes issues, and issues verdicts."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        super().__init__(name="Lead Architect", role="PR Review Orchestrator & Synthesizer", llm_client=llm_client)
        self.security_agent = SecurityAgent(llm_client=self.llm)
        self.quality_agent = QualityAgent(llm_client=self.llm)
        self.test_agent = TestAgent(llm_client=self.llm)
        self.fixer_agent = FixerAgent(llm_client=self.llm)

    @property
    def system_prompt(self) -> str:
        return """You are Lead Architect, the Chief Code Reviewer and Tech Lead.
Your role is to evaluate findings from the Security Auditor, Quality Engineer, and QA Specialist to synthesize a unified executive summary, compute a risk score (0-100), and determine the final PR verdict:
- APPROVE: Safe to merge, no major security or logic flaws.
- COMMENT: Minor suggestions, improvements or missing edge-case tests.
- REQUEST_CHANGES: Critical or high security flaws, data loss risks, or severe performance degradation.

You must output a JSON object:
{
  "executive_summary": "Concise 2-3 paragraph executive summary of the changes and overall quality",
  "risk_score": 35,
  "verdict": "APPROVE" | "COMMENT" | "REQUEST_CHANGES"
}
"""

    def review(self, diff_context: DiffContext) -> AgentReviewResult:
        # Implemented for BaseAgent compliance
        report = self.review_pr(diff_context)
        return AgentReviewResult(
            agent_name=self.name,
            agent_role=self.role,
            summary=report.executive_summary,
            issues=report.issues,
            patches=report.patches,
            generated_tests=report.generated_tests,
        )

    def review_pr(self, diff_context: DiffContext) -> PRReviewReport:
        """Runs the full multi-agent swarm pipeline over the diff."""
        # 1. Run specialized review agents
        sec_res = self.security_agent.review(diff_context)
        qual_res = self.quality_agent.review(diff_context)
        test_res = self.test_agent.review(diff_context)

        agent_results = [sec_res, qual_res, test_res]

        # 2. Aggregate and Sanitize detected issues (Self-Reflection Pass)
        all_issues: List[CodeIssue] = []
        all_issues.extend(sec_res.issues)
        all_issues.extend(qual_res.issues)
        all_issues.extend(test_res.issues)

        from pr_sentinel.core.reflection_engine import mistake_memory

        valid_file_paths = {f.target_file for f in diff_context.files}
        valid_file_paths.update({f.source_file for f in diff_context.files})

        sanitized_issues: List[CodeIssue] = []
        seen_issue_keys = set()

        for iss in all_issues:
            # Self-Reflection: Filter hallucinated files if diff has known files
            if valid_file_paths and iss.file_path not in valid_file_paths and iss.file_path != "unknown":
                # Check if it's a basename match
                matched = next((vf for vf in valid_file_paths if vf.endswith(iss.file_path) or iss.file_path.endswith(vf)), None)
                if matched:
                    iss.file_path = matched
                else:
                    # Record hallucination mistake
                    mistake_memory.record_mistake(
                        category="HALLUCINATED_FILE",
                        agent_name=iss.agent_name,
                        description=f"Agent hallucinated non-existent file '{iss.file_path}' not present in PR diff.",
                        flawed_approach=f"❌ Flagging '{iss.title}' on file '{iss.file_path}' which does not exist in the diff.",
                        positive_exemplar=f"✅ Inspect list of modified files first and only attribute findings to: {list(valid_file_paths)}.",
                        corrective_rule="Only report issues for files explicitly listed in the modified diff context.",
                    )
                    continue

            # Deduplication pass
            issue_key = f"{iss.file_path}:{iss.line_start}:{iss.title.lower()}"
            if issue_key in seen_issue_keys:
                continue
            seen_issue_keys.add(issue_key)
            sanitized_issues.append(iss)

        # 3. Filter by severity threshold
        severity_rank = {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
        }
        min_rank = severity_rank.get(settings.severity_threshold, 1)
        filtered_issues = [i for i in sanitized_issues if severity_rank.get(i.severity, 0) >= min_rank]

        # 4. Generate Auto-Fixes if enabled
        patches = []
        if settings.enable_auto_fix and filtered_issues:
            patches = self.fixer_agent.synthesize_fixes(diff_context, filtered_issues)

        # 5. Synthesize Executive Summary & Verdict
        diff_text = self._format_diff_for_prompt(diff_context)
        issues_text = "\n".join([f"- [{i.severity.value}] {i.title} in {i.file_path}: {i.description}" for i in filtered_issues]) or "No major issues flagged."

        synth_prompt = (
            f"PR Title: {diff_context.pr_title or 'Code Change'}\n"
            f"Files Changed: {len(diff_context.files)}, Lines: +{diff_context.total_added}, -{diff_context.total_deleted}\n\n"
            f"Issues Flagged by Agents:\n{issues_text}\n\n"
            f"Please synthesize an executive review, risk score (0-100), and final verdict."
        )

        has_critical = any(i.severity in [Severity.CRITICAL, Severity.HIGH] for i in filtered_issues)
        default_verdict = "REQUEST_CHANGES" if has_critical else ("COMMENT" if filtered_issues else "APPROVE")
        default_risk = 85 if has_critical else (40 if filtered_issues else 10)

        mock_fallback = {
            "executive_summary": "The code review is complete. Automated checks passed and structure is compliant.",
            "risk_score": default_risk,
            "verdict": default_verdict,
        }

        synthesis_data = self.llm.complete_structured(
            prompt=synth_prompt,
            system_prompt=self.get_augmented_system_prompt(),
            mock_fallback=mock_fallback,
        )

        verdict_str = synthesis_data.get("verdict", default_verdict).upper()
        try:
            verdict = PRVerdict(verdict_str)
        except ValueError:
            verdict = PRVerdict.COMMENT

        risk_score = int(synthesis_data.get("risk_score", default_risk))
        risk_score = max(0, min(100, risk_score))

        return PRReviewReport(
            title=diff_context.pr_title or "PR-Sentinel Automated Review",
            target_ref=diff_context.branch_name,
            risk_score=risk_score,
            verdict=verdict,
            executive_summary=synthesis_data.get("executive_summary", "Review complete."),
            total_issues=len(filtered_issues),
            issues=filtered_issues,
            patches=patches,
            generated_tests=test_res.generated_tests,
            agent_results=agent_results,
        )
