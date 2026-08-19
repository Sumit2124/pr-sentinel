import os
import subprocess
from typing import Optional, Dict, Any
from git import Repo, InvalidGitRepositoryError
from github import Github, Auth
from pr_sentinel.config import settings
from pr_sentinel.core.models import DiffContext, PRReviewReport
from pr_sentinel.core.diff_parser import DiffParser


class GitProvider:
    """Manages Git repository operations, diff extraction, patch application, and GitHub API interactions."""

    def __init__(self, repo_path: str = "."):
        self.repo_path = os.path.abspath(repo_path)
        self._repo: Optional[Repo] = None
        try:
            self._repo = Repo(self.repo_path, search_parent_directories=True)
        except InvalidGitRepositoryError:
            self._repo = None

    @property
    def is_git_repo(self) -> bool:
        return self._repo is not None

    def get_current_branch(self) -> Optional[str]:
        if not self._repo:
            return None
        try:
            return self._repo.active_branch.name
        except Exception:
            return "DETACHED_HEAD"

    def get_local_diff(self, base_ref: Optional[str] = None, staged: bool = False) -> DiffContext:
        """Extract diff from the local git working tree."""
        if not self._repo:
            raise ValueError(f"Directory '{self.repo_path}' is not a valid Git repository.")

        if base_ref:
            raw_diff = self._repo.git.diff(base_ref)
        elif staged:
            raw_diff = self._repo.git.diff("--cached")
        else:
            # Check unstaged first, fallback to HEAD~1 if working directory is clean
            raw_diff = self._repo.git.diff()
            if not raw_diff.strip():
                try:
                    raw_diff = self._repo.git.diff("HEAD~1")
                except Exception:
                    pass

        branch = self.get_current_branch()
        return DiffParser.parse_diff(raw_diff, branch_name=branch)

    def apply_patch(self, patch_content: str) -> Dict[str, Any]:
        """Applies a unified patch to the local repository."""
        if not self.is_git_repo:
            return {"success": False, "error": "Not a git repository."}

        try:
            process = subprocess.run(
                ["git", "apply", "--ignore-whitespace", "-"],
                input=patch_content,
                text=True,
                capture_output=True,
                cwd=self.repo_path,
            )
            if process.returncode == 0:
                return {"success": True, "message": "Patch applied successfully."}
            else:
                return {"success": False, "error": process.stderr}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fetch_github_pr_diff(self, pr_url: str) -> DiffContext:
        """Fetches diff and PR metadata from a GitHub PR URL (e.g. https://github.com/owner/repo/pull/123)."""
        import re
        match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
        if not match:
            raise ValueError("Invalid GitHub PR URL. Expected format: https://github.com/owner/repo/pull/123")

        owner, repo_name, pr_number = match.group(1), match.group(2), int(match.group(3))
        
        token = settings.github_token or os.environ.get("GITHUB_TOKEN")
        gh = Github(auth=Auth.Token(token)) if token else Github()
        repo = gh.get_repo(f"{owner}/{repo_name}")
        pr = repo.get_pull(pr_number)

        # Get diff via requests/PyGithub
        import urllib.request
        req = urllib.request.Request(pr.diff_url)
        if token:
            req.add_header("Authorization", f"token {token}")
        req.add_header("Accept", "application/vnd.github.v3.diff")
        
        with urllib.request.urlopen(req) as resp:
            raw_diff = resp.read().decode("utf-8")

        diff_ctx = DiffParser.parse_diff(raw_diff, branch_name=pr.head.ref, pr_title=pr.title)
        diff_ctx.pr_description = pr.body or ""
        return diff_ctx

    def post_github_pr_review(self, pr_url: str, report: PRReviewReport) -> bool:
        """Posts review comments and summary back to a GitHub PR."""
        import re
        match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
        if not match:
            return False

        owner, repo_name, pr_number = match.group(1), match.group(2), int(match.group(3))
        token = settings.github_token or os.environ.get("GITHUB_TOKEN")
        if not token:
            print("Warning: GITHUB_TOKEN is not configured. Cannot post comment to PR.")
            return False

        gh = Github(auth=Auth.Token(token))
        repo = gh.get_repo(f"{owner}/{repo_name}")
        pr = repo.get_pull(pr_number)

        # Format markdown body
        comment_body = self.format_markdown_report(report)
        pr.create_issue_comment(comment_body)
        return True

    @staticmethod
    def format_markdown_report(report: PRReviewReport) -> str:
        """Formats the review report into clean GitHub Flavored Markdown."""
        verdict_badge = {
            "APPROVE": "🟢 **APPROVED**",
            "COMMENT": "🟡 **COMMENT**",
            "REQUEST_CHANGES": "🔴 **REQUEST CHANGES**",
        }.get(report.verdict.value, report.verdict.value)

        lines = [
            f"# 🛡️ PR-Sentinel Code Review Report",
            f"",
            f"**Verdict**: {verdict_badge} | **Risk Score**: `{report.risk_score}/100` | **Issues Found**: `{len(report.issues)}`",
            f"",
            f"## 📋 Executive Summary",
            f"{report.executive_summary}",
            f"",
        ]

        if report.issues:
            lines.append("## 🔍 Detailed Findings")
            for i, issue in enumerate(report.issues, start=1):
                sev_icon = {
                    "CRITICAL": "🚨 `CRITICAL`",
                    "HIGH": "🔴 `HIGH`",
                    "MEDIUM": "🟡 `MEDIUM`",
                    "LOW": "🔵 `LOW`",
                    "INFO": "ℹ️ `INFO`",
                }.get(issue.severity.value, issue.severity.value)

                lines.append(f"### {i}. [{sev_icon}] {issue.title}")
                lines.append(f"- **File**: `{issue.file_path}` (Line {issue.line_start})")
                lines.append(f"- **Category**: `{issue.category.value}` (Audited by `{issue.agent_name}`)")
                if issue.cwe_id:
                    lines.append(f"- **CWE**: `{issue.cwe_id}`")
                lines.append(f"- **Description**: {issue.description}")
                lines.append(f"- **💡 Suggested Fix**: {issue.suggestion}")
                if issue.code_snippet:
                    lines.append(f"```\n{issue.code_snippet}\n```")
                lines.append("")

        if report.patches:
            lines.append("## 🛠️ Automated Fix Patches")
            for patch in report.patches:
                lines.append(f"#### Patch for `{patch.file_path}` (Confidence: {int(patch.confidence_score * 100)}%)")
                lines.append(f"> {patch.rationale}")
                lines.append(f"```diff\n{patch.unified_diff}\n```")
                lines.append("")

        if report.generated_tests:
            lines.append("## 🧪 Suggested Regression & Unit Tests")
            for test in report.generated_tests:
                lines.append(f"#### Test: `{test.test_file_path}` ({test.framework})")
                lines.append(f"> {test.description}")
                lines.append(f"```python\n{test.test_code}\n```")
                lines.append("")

        lines.append("---")
        lines.append("💡 **Auto-Fix Option**: Reply with `/sentinel fix` on this PR to automatically apply and commit all recommended patches directly to this branch.")
        lines.append("")
        lines.append("*Generated automatically by [PR-Sentinel](https://github.com/your-username/pr-sentinel) multi-agent code analysis.*")
        return "\n".join(lines)

    def commit_fixes_to_pr(self, pr_url: str, report: PRReviewReport) -> Dict[str, Any]:
        """Applies generated patches and commits them to the PR branch."""
        import re
        match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
        if not match:
            return {"success": False, "error": "Invalid PR URL"}

        owner, repo_name, pr_number = match.group(1), match.group(2), int(match.group(3))
        token = settings.github_token or os.environ.get("GITHUB_TOKEN")
        if not token:
            return {"success": False, "error": "Missing GITHUB_TOKEN"}

        if not report.patches:
            return {"success": False, "message": "No patches available to apply."}

        applied_count = 0
        for patch in report.patches:
            res = self.apply_patch(patch.unified_diff)
            if res.get("success"):
                applied_count += 1

        if applied_count == 0:
            return {"success": False, "error": "Failed to apply patches cleanly to working tree."}

        # Commit and push via git CLI
        try:
            subprocess.run(["git", "config", "user.name", "PR-Sentinel[bot]"], check=True)
            subprocess.run(["git", "config", "user.email", "bot@pr-sentinel.local"], check=True)
            subprocess.run(["git", "add", "-A"], check=True)
            subprocess.run(["git", "commit", "-m", "fix(pr-sentinel): auto-apply security & quality patches"], check=True)
            subprocess.run(["git", "push"], check=True)

            # Post confirmation comment
            gh = Github(auth=Auth.Token(token))
            repo = gh.get_repo(f"{owner}/{repo_name}")
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(f"🤖 **PR-Sentinel Auto-Fix Applied**: Successfully committed and pushed `{applied_count}` fix patches to `{pr.head.ref}`.")

            return {"success": True, "applied_count": applied_count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def format_agent_rectification_prompt(report: PRReviewReport) -> str:
        """Formats the review findings into an actionable, structured prompt file for AI Coding Agents."""
        lines = [
            "# 🤖 AI Agent Rectification Plan",
            "",
            "> **Instructions for AI Coding Assistant (Cursor / Claude Code / Aider / Copilot / Antigravity)**:",
            "> You are tasked with rectifying the following detected code issues and applying the necessary security and quality fixes.",
            "",
            "## 🎯 Objective",
            f"Review Verdict: `{report.verdict.value}` | Risk Score: `{report.risk_score}/100` | Target Issues: `{len(report.issues)}`",
            "",
            "## 📋 Task List & Issues to Fix",
        ]

        for i, issue in enumerate(report.issues, 1):
            lines.append(f"### Issue #{i}: {issue.title}")
            lines.append(f"- **Target File**: `{issue.file_path}`")
            lines.append(f"- **Line Number**: {issue.line_start}")
            lines.append(f"- **Severity**: `{issue.severity.value}`")
            lines.append(f"- **Category**: `{issue.category.value}`")
            if issue.cwe_id:
                lines.append(f"- **CWE ID**: `{issue.cwe_id}`")
            lines.append(f"- **Root Cause**: {issue.description}")
            lines.append(f"- **Fix Instructions**: {issue.suggestion}")
            if issue.code_snippet:
                lines.append(f"- **Vulnerable Snippet**:\n```\n{issue.code_snippet}\n```")
            lines.append("")

        if report.patches:
            lines.append("## 🛠️ Reference Patches to Apply")
            for j, patch in enumerate(report.patches, 1):
                lines.append(f"#### Patch #{j} for `{patch.file_path}`")
                lines.append(f"Rationale: {patch.rationale}")
                lines.append(f"```diff\n{patch.unified_diff}\n```")
                lines.append("")

        if report.generated_tests:
            lines.append("## 🧪 Required Unit & Regression Tests")
            for k, test in enumerate(report.generated_tests, 1):
                lines.append(f"#### Test File: `{test.test_file_path}`")
                lines.append(f"Goal: {test.description}")
                lines.append(f"```python\n{test.test_code}\n```")
                lines.append("")

        lines.append("## ✅ Verification Checklist for Agent")
        lines.append("1. [ ] Apply the necessary fixes to all flagged files without introducing breaking changes.")
        lines.append("2. [ ] Ensure all input validations and parameterized queries are strictly enforced.")
        lines.append("3. [ ] Add the proposed unit tests to prevent future regression.")
        lines.append("4. [ ] Run the test suite and verify that all tests pass cleanly.")

        return "\n".join(lines)


