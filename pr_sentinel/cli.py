import os
import sys
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown

from pr_sentinel import __version__
from pr_sentinel.config import settings, Severity
from pr_sentinel.core.git_provider import GitProvider
from pr_sentinel.core.diff_parser import DiffParser
from pr_sentinel.core.models import DiffContext, PRReviewReport, PRVerdict
from pr_sentinel.agents.lead_reviewer import LeadReviewerAgent
from pr_sentinel.llm.client import LLMClient

app = typer.Typer(
    name="pr-sentinel",
    help="🛡️ PR-Sentinel: Multi-Agent AI Code Reviewer & PR Auto-Fixer Bot",
    add_completion=False,
)
console = Console()


def display_report_rich(report: PRReviewReport):
    """Renders the review report beautifully in the terminal using Rich."""
    verdict_styles = {
        PRVerdict.APPROVE: ("green", "✅ APPROVED"),
        PRVerdict.COMMENT: ("yellow", "💬 COMMENT / CHANGES SUGGESTED"),
        PRVerdict.REQUEST_CHANGES: ("red", "🚨 REQUEST CHANGES"),
    }
    color, text = verdict_styles.get(report.verdict, ("white", report.verdict.value))

    # Header Panel
    console.print(
        Panel(
            f"[bold {color}]Verdict: {text}[/]\n"
            f"[bold]Risk Score:[/] [{color}]{report.risk_score}/100[/] | "
            f"[bold]Issues Found:[/] {report.total_issues} | "
            f"[bold]Patches Generated:[/] {len(report.patches)}",
            title=f"🛡️ PR-Sentinel Review Report (v{__version__})",
            border_style=color,
        )
    )

    # Executive Summary
    console.print(Panel(report.executive_summary, title="📋 Executive Summary", border_style="blue"))

    # Issues Table
    if report.issues:
        table = Table(title="🔍 Identified Issues", show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Severity", width=12)
        table.add_column("Category", width=15)
        table.add_column("File & Line", width=25)
        table.add_column("Agent", width=18)
        table.add_column("Summary")

        sev_colors = {
            Severity.CRITICAL: "bold red",
            Severity.HIGH: "red",
            Severity.MEDIUM: "yellow",
            Severity.LOW: "blue",
            Severity.INFO: "dim",
        }

        for idx, issue in enumerate(report.issues, start=1):
            scolor = sev_colors.get(issue.severity, "white")
            table.add_row(
                str(idx),
                f"[{scolor}]{issue.severity.value}[/]",
                issue.category.value,
                f"{issue.file_path}:{issue.line_start}",
                issue.agent_name,
                f"[bold]{issue.title}[/]\n{issue.description}",
            )
        console.print(table)
    else:
        console.print("[bold green]✨ No code quality or security issues detected![/]\n")

    # Patches
    if report.patches:
        console.print("\n[bold cyan]🛠️ Automated Fix Patches:[/]")
        for idx, patch in enumerate(report.patches, start=1):
            console.print(f"\n[bold yellow]Patch #{idx} for {patch.file_path}[/] (Confidence: {int(patch.confidence_score*100)}%)")
            console.print(f"[italic]{patch.rationale}[/]")
            syntax = Syntax(patch.unified_diff, "diff", theme="monokai", line_numbers=False)
            console.print(syntax)

    # Generated Tests
    if report.generated_tests:
        console.print("\n[bold magenta]🧪 Suggested Unit & Regression Tests:[/]")
        for test in report.generated_tests:
            console.print(f"\n[bold]{test.test_file_path}[/] ({test.description})")
            syntax = Syntax(test.test_code, "python", theme="monokai", line_numbers=True)
            console.print(syntax)


@app.command()
def review(
    pr_url: Optional[str] = typer.Option(None, "--pr", help="GitHub PR URL (e.g. https://github.com/org/repo/pull/1)"),
    diff_file: Optional[str] = typer.Option(None, "--diff-file", help="Path to a raw .diff or .patch file"),
    staged: bool = typer.Option(False, "--staged", help="Review currently staged git changes"),
    base: Optional[str] = typer.Option(None, "--base", help="Git base branch/ref to diff against (e.g. main)"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model (e.g. gemini/gemini-1.5-flash, gpt-4o)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save markdown report to file"),
    post_comment: bool = typer.Option(False, "--post-comment", help="Post review comment to GitHub PR if --pr is provided"),
):
    """Run the multi-agent code review swarm over a Git diff or GitHub PR."""
    git_provider = GitProvider()

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        transient=True,
    ) as progress:
        # 1. Fetch Diff Context
        progress.add_task(description="Extracting code diff...", total=None)
        if pr_url:
            diff_ctx = git_provider.fetch_github_pr_diff(pr_url)
        elif diff_file:
            with open(diff_file, "r", encoding="utf-8") as f:
                raw_diff = f.read()
            diff_ctx = DiffParser.parse_diff(raw_diff)
        else:
            if not git_provider.is_git_repo:
                console.print("[bold red]Error:[/] Current directory is not a Git repo. Use --diff-file or --pr.")
                raise typer.Exit(code=1)
            diff_ctx = git_provider.get_local_diff(base_ref=base, staged=staged)

        if not diff_ctx.files and not diff_ctx.raw_diff.strip():
            console.print("[bold yellow]Notice:[/] No diff changes found to review.")
            return

        # 2. Run Review Swarm
        progress.add_task(description="Swarm Agents analyzing security, quality, and tests...", total=None)
        llm_client = LLMClient(model=model) if model else None
        lead_agent = LeadReviewerAgent(llm_client=llm_client)
        report = lead_agent.review_pr(diff_ctx)

    # 3. Display Report
    display_report_rich(report)

    # 4. Save markdown if requested
    if output:
        md_content = GitProvider.format_markdown_report(report)
        with open(output, "w", encoding="utf-8") as f:
            f.write(md_content)
        console.print(f"\n[green]✅ Report successfully saved to:[/] {output}")

    # 5. Post to GitHub PR if requested
    if post_comment and pr_url:
        success = git_provider.post_github_pr_review(pr_url, report)
        if success:
            console.print("[bold green]✅ Review comment successfully posted to GitHub PR![/]")
        else:
            console.print("[bold red]❌ Failed to post comment to GitHub PR.[/]")


@app.command()
def fix(
    diff_file: Optional[str] = typer.Option(None, "--diff-file", help="Path to a raw .diff file"),
    staged: bool = typer.Option(False, "--staged", help="Analyze staged git changes"),
    apply_fix: bool = typer.Option(False, "--apply", "-a", help="Automatically apply patch to repository"),
):
    """Analyze code and interactively generate & apply auto-fix patches."""
    git_provider = GitProvider()
    if diff_file:
        with open(diff_file, "r", encoding="utf-8") as f:
            raw_diff = f.read()
        diff_ctx = DiffParser.parse_diff(raw_diff)
    else:
        diff_ctx = git_provider.get_local_diff(staged=staged)

    lead_agent = LeadReviewerAgent()
    report = lead_agent.review_pr(diff_ctx)
    display_report_rich(report)

    if not report.patches:
        console.print("\n[yellow]No fix patches available to apply.[/]")
        return

    for idx, patch in enumerate(report.patches, 1):
        console.print(f"\n[bold cyan]Patch #{idx} for {patch.file_path}[/]")
        should_apply = apply_fix or typer.confirm(f"Do you want to apply this patch to '{patch.file_path}'?")
        if should_apply:
            res = git_provider.apply_patch(patch.unified_diff)
            if res.get("success"):
                console.print(f"[bold green]✅ Successfully applied patch to {patch.file_path}[/]")
            else:
                console.print(f"[bold red]❌ Failed to apply patch:[/] {res.get('error')}")


@app.command()
def scan(
    path: str = typer.Argument(".", help="Directory or repository root path to scan"),
    max_files: int = typer.Option(50, "--max-files", "-m", help="Maximum number of files to audit"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model to use"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save markdown audit report to file"),
):
    """Scan and audit an entire repository directory (AppSec, Code Smells, Architecture)."""
    from pr_sentinel.core.repo_scanner import RepoScanner

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"Scanning repository files in '{path}'...", total=None)
        diff_ctx = RepoScanner.scan_directory(directory_path=path, max_files=max_files)

        if not diff_ctx.files:
            console.print(f"[bold yellow]Notice:[/] No supported source files found in '{path}'.")
            return

        progress.add_task(description=f"Running Multi-Agent Audit over {len(diff_ctx.files)} files ({diff_ctx.total_added} lines)...", total=None)
        llm_client = LLMClient(model=model) if model else None
        lead_agent = LeadReviewerAgent(llm_client=llm_client)
        report = lead_agent.review_pr(diff_ctx)

    display_report_rich(report)

    if output:
        md_content = GitProvider.format_markdown_report(report)
        with open(output, "w", encoding="utf-8") as f:
            f.write(md_content)
        console.print(f"\n[green]✅ Full Codebase Audit successfully saved to:[/] {output}")

@app.command(name="bot-fix")
def bot_fix(
    pr_url: str = typer.Option(..., "--pr", help="GitHub PR URL to analyze and apply fixes to"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model"),
):
    """(CI/Bot Mode) Analyze a GitHub PR and automatically commit recommended fixes directly to the branch."""
    git_provider = GitProvider()
    diff_ctx = git_provider.fetch_github_pr_diff(pr_url)

    llm_client = LLMClient(model=model) if model else None
    lead_agent = LeadReviewerAgent(llm_client=llm_client)
    report = lead_agent.review_pr(diff_ctx)

    if not report.patches:
        console.print("[yellow]No auto-fix patches generated for this PR.[/]")
        return

    result = git_provider.commit_fixes_to_pr(pr_url, report)
    if result.get("success"):
        console.print(f"[bold green]✅ Successfully committed and pushed {result.get('applied_count')} patches to PR branch![/]")
    else:
        console.print(f"[bold red]❌ Failed to commit fixes:[/] {result.get('error')}")


@app.command()
def sample():
    """Run a showcase review on an intentionally vulnerable sample diff."""
    sample_diff = """diff --git a/app/api/auth.py b/app/api/auth.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/app/api/auth.py
@@ -0,0 +1,24 @@
+import sqlite3
+import os
+
+ADMIN_SECRET_KEY = "sk-live-93821093810293810293"
+
+def get_user_profile(username):
+    conn = sqlite3.connect("users.db")
+    cursor = conn.cursor()
+    # Raw SQL query concatenation
+    query = "SELECT id, username, email FROM users WHERE username = '" + username + "'"
+    cursor.execute(query)
+    return cursor.fetchone()
+
+def read_user_file(file_path):
+    # Unsanitized path traversal
+    with open("/data/uploads/" + file_path, "r") as f:
+        return f.read()
+"""
+    console.print(Panel("[bold yellow]Running PR-Sentinel Swarm on a sample buggy diff containing SQL Injection, Hardcoded Secret, and Path Traversal...[/]"))
+    diff_ctx = DiffParser.parse_diff(sample_diff, pr_title="Add Auth & File Endpoints")
+    lead_agent = LeadReviewerAgent()
+    report = lead_agent.review_pr(diff_ctx)
+    display_report_rich(report)


