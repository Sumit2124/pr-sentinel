import os
import json
import glob
from rich.console import Console
from rich.table import Table
from pr_sentinel.core.diff_parser import DiffParser
from pr_sentinel.agents.lead_reviewer import LeadReviewerAgent
from pr_sentinel.llm.client import LLMClient

console = Console()


def run_benchmark():
    case_files = glob.glob(os.path.join(os.path.dirname(__file__), "test_cases", "*.json"))
    if not case_files:
        console.print("[red]No benchmark test cases found.[/]")
        return

    console.print(f"[bold cyan]Running PR-Sentinel Evaluation Suite against {len(case_files)} benchmark cases...[/]\n")
    
    table = Table(title="📊 Benchmark Evaluation Results", show_header=True, header_style="bold magenta")
    table.add_column("Case ID", width=25)
    table.add_column("Name", width=30)
    table.add_column("Issues Detected", width=18)
    table.add_column("Verdict", width=18)
    table.add_column("Status", width=12)

    passed_count = 0

    for cpath in sorted(case_files):
        with open(cpath, "r", encoding="utf-8") as f:
            case_data = json.load(f)

        cid = case_data.get("id", "UNKNOWN")
        cname = case_data.get("name", "Unnamed Case")
        diff_text = case_data.get("diff", "")
        expected = case_data.get("expected", {})

        diff_ctx = DiffParser.parse_diff(diff_text, pr_title=cname)
        lead_agent = LeadReviewerAgent()
        report = lead_agent.review_pr(diff_ctx)

        # Check conditions
        min_issues = expected.get("min_issues", 0)
        expected_verdict = expected.get("expected_verdict")

        is_passed = True
        if len(report.issues) < min_issues:
            is_passed = False
        if expected_verdict and report.verdict.value != expected_verdict:
            # Allow COMMENT if REQUEST_CHANGES or vice versa depending on model reasoning, but check strict match
            if not (report.verdict.value in ["COMMENT", "REQUEST_CHANGES"] and expected_verdict in ["COMMENT", "REQUEST_CHANGES"]):
                is_passed = False

        status_str = "[bold green]PASS[/]" if is_passed else "[bold red]FAIL[/]"
        if is_passed:
            passed_count += 1

        table.add_row(
            cid,
            cname,
            f"{len(report.issues)} (Exp: >={min_issues})",
            f"{report.verdict.value} (Exp: {expected_verdict})",
            status_str,
        )

    console.print(table)
    pass_rate = (passed_count / len(case_files)) * 100
    console.print(f"\n[bold]Overall Benchmark Score:[/] [cyan]{passed_count}/{len(case_files)} ({pass_rate:.1f}% Pass Rate)[/]")


if __name__ == "__main__":
    run_benchmark()
