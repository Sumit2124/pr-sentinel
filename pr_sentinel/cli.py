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
    agent_prompt: Optional[str] = typer.Option(None, "--agent-prompt", help="Save AI-Agent rectification plan prompt file (.md)"),
    post_comment: bool = typer.Option(False, "--post-comment", help="Post review comment to GitHub PR if --pr is provided"),
    strict_gate: bool = typer.Option(False, "--strict-gate", "--fail-on-risk", help="Exit with code 1 if verdict is REQUEST_CHANGES (blocks PR merge in CI)"),
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

    # 5. Save Agent Rectification Prompt if requested
    if agent_prompt:
        prompt_content = GitProvider.format_agent_rectification_prompt(report)
        with open(agent_prompt, "w", encoding="utf-8") as f:
            f.write(prompt_content)
        console.print(f"[green]🤖 AI Agent Rectification Prompt saved to:[/] {agent_prompt}")

    # 6. Post to GitHub PR if requested
    if post_comment and pr_url:
        success = git_provider.post_github_pr_review(pr_url, report)
        if success:
            console.print("[bold green]✅ Review comment successfully posted to GitHub PR![/]")
        else:
            console.print("[bold red]❌ Failed to post comment to GitHub PR.[/]")

    # 7. Strict CI Gate Enforcement
    if strict_gate and report.verdict == PRVerdict.REQUEST_CHANGES:
        console.print("\n[bold red]🚨 PR-Sentinel Gatekeeper FAILED:[/] High-risk issues detected. Merge blocked.")
        raise typer.Exit(code=1)


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
    path: str = typer.Argument(".", help="Directory path to scan (or ignored if --repo is used)"),
    repo_url: Optional[str] = typer.Option(None, "--repo", "-r", help="Remote GitHub repository URL (e.g. https://github.com/owner/repo)"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Remote repository branch to audit (e.g. main, dev)"),
    max_files: int = typer.Option(50, "--max-files", "-m", help="Maximum number of files to audit"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model to use"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save markdown audit report to file"),
    agent_prompt: Optional[str] = typer.Option(None, "--agent-prompt", help="Save AI-Agent rectification plan prompt file (.md)"),
):
    """Scan and audit an entire local directory or remote GitHub repository."""
    from pr_sentinel.core.repo_scanner import RepoScanner

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        transient=True,
    ) as progress:
        if repo_url:
            progress.add_task(description=f"Cloning & scanning remote repo '{repo_url}' (branch: {branch or 'default'})...", total=None)
            diff_ctx = RepoScanner.scan_remote_repo(repo_url=repo_url, branch=branch, max_files=max_files)
        else:
            progress.add_task(description=f"Scanning local directory files in '{path}'...", total=None)
            diff_ctx = RepoScanner.scan_directory(directory_path=path, max_files=max_files)

        if not diff_ctx.files:
            console.print(f"[bold yellow]Notice:[/] No supported source files found.")
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

    if agent_prompt:
        prompt_content = GitProvider.format_agent_rectification_prompt(report)
        with open(agent_prompt, "w", encoding="utf-8") as f:
            f.write(prompt_content)
        console.print(f"[green]🤖 AI Agent Rectification Prompt saved to:[/] {agent_prompt}")


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


# Mistakes & Learned Guardrails Sub-Commands
mistakes_app = typer.Typer(name="mistakes", help="🧠 Manage learned guardrails and mistake memory to prevent repeat errors")
app.add_typer(mistakes_app, name="mistakes")


@mistakes_app.command("list")
def list_mistakes():
    """List all recorded mistakes and their positive transformation exemplars."""
    from pr_sentinel.core.reflection_engine import mistake_memory
    records = mistake_memory.list_mistakes()

    if not records:
        console.print("[green]✨ No mistakes recorded in memory yet. Agents are operating with base rubrics.[/]")
        return

    table = Table(title="🧠 Learned (Negative ➔ Positive) Calibration Exemplars", show_header=True, header_style="bold purple")
    table.add_column("ID", width=8)
    table.add_column("Category & Agent", width=22)
    table.add_column("❌ Negative (Flawed Decision to Avoid)", width=35)
    table.add_column("✅ Positive (Correct Action to Take)", width=40)
    table.add_column("💡 Golden Principle", width=30)

    for r in records:
        table.add_row(
            r.id,
            f"[bold yellow]{r.category}[/]\n[cyan]{r.agent_name}[/]",
            f"[red]{r.flawed_approach}[/]",
            f"[green]{r.positive_exemplar}[/]",
            f"[bold white]{r.corrective_rule}[/]",
        )
    console.print(table)


@mistakes_app.command("teach")
def teach_rule(
    flawed: str = typer.Option(..., "--flawed", "-f", help="❌ The flawed decision or false positive to avoid (Negative)"),
    positive: str = typer.Option(..., "--positive", "-p", help="✅ The correct action or golden behavior to take (Positive)"),
    rule: str = typer.Option(..., "--rule", "-r", help="💡 The generalized rule of thumb"),
    agent: str = typer.Option("ALL", "--agent", "-a", help="Agent to calibrate (e.g. 'SecOps Sentinel', 'ALL')"),
    category: str = typer.Option("FALSE_POSITIVE", "--category", "-c", help="Category (FALSE_POSITIVE, MALFORMED_PATCH, etc.)"),
):
    """Teach the agents a new Negative ➔ Positive transformation exemplar."""
    from pr_sentinel.core.reflection_engine import mistake_memory
    record = mistake_memory.record_mistake(
        category=category,
        agent_name=agent,
        description=f"User taught calibration: {rule}",
        flawed_approach=f"❌ {flawed}",
        positive_exemplar=f"✅ {positive}",
        corrective_rule=rule,
    )
    console.print(f"[bold green]✅ Successfully recorded (Negative ➔ Positive) Exemplar (ID: {record.id})![/]")
    console.print(f"Agents will now use this case study as a few-shot exemplar during evaluations.")


@mistakes_app.command("clear")
def clear_mistakes():
    """Clear all stored mistake memory."""
    from pr_sentinel.core.reflection_engine import mistake_memory
    mistake_memory.clear_memory()
    console.print("[bold yellow]🧹 Mistake memory cleared.[/]")


@app.command(name="skill-update")
def skill_update(
    skill_file: str = typer.Option(..., "--skill", "-s", help="Path to existing SKILL.md file to evolve"),
    pr_url: Optional[str] = typer.Option(None, "--pr", help="GitHub PR URL whose resolutions should train the skill"),
    diff_file: Optional[str] = typer.Option(None, "--diff-file", "-d", help="Path to raw diff/patch file of resolved changes"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Path to save updated SKILL.md (defaults to overwriting input)"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model to use"),
):
    """Refactor and evolve an AI Agent SKILL.md file using resolved PR review lessons."""
    from pr_sentinel.core.skill_updater import SkillUpdater

    if not os.path.exists(skill_file):
        console.print(f"[bold red]Error:[/] Skill file '{skill_file}' not found.")
        raise typer.Exit(code=1)

    with open(skill_file, "r", encoding="utf-8") as f:
        skill_content = f.read()

    git_provider = GitProvider()
    if pr_url:
        diff_ctx = git_provider.fetch_github_pr_diff(pr_url)
    elif diff_file:
        with open(diff_file, "r", encoding="utf-8") as f:
            raw_diff = f.read()
        diff_ctx = DiffParser.parse_diff(raw_diff)
    else:
        diff_ctx = git_provider.get_local_diff()

    llm_client = LLMClient(model=model) if model else None
    lead_agent = LeadReviewerAgent(llm_client=llm_client)
    report = lead_agent.review_pr(diff_ctx)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"Evolving skill instructions from {len(report.issues)} resolved issues...", total=None)
        updater = SkillUpdater(llm_client=llm_client)
        result = updater.update_skill_from_report(skill_content=skill_content, report=report, diff_context=diff_ctx)

    console.print(Panel(result.get("summary_of_changes", "Skill updated with defensive rules."), title="⚡ Skill Evolution Summary", border_style="green"))
    console.print(f"[bold cyan]Efficiency Impact:[/] {result.get('efficiency_gain_notes', 'Higher coding agent accuracy.')}")

    target_path = output or skill_file
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(result.get("updated_skill_content", skill_content))

    console.print(f"\n[bold green]✅ Updated SKILL.md successfully saved to:[/] {target_path}")




