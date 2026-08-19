import os
import streamlit as st
from pr_sentinel.config import settings, Severity
from pr_sentinel.core.diff_parser import DiffParser
from pr_sentinel.core.git_provider import GitProvider
from pr_sentinel.core.models import PRVerdict
from pr_sentinel.agents.lead_reviewer import LeadReviewerAgent
from pr_sentinel.llm.client import LLMClient

# Page configuration
st.set_page_config(
    page_title="PR-Sentinel | Multi-Agent Code Reviewer",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🛡️ PR-Sentinel: Multi-Agent Code Reviewer & Auto-Fixer")
st.caption("Autonomous AI agent swarm auditing security, quality, test coverage, and generating git patches.")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Swarm Settings")
    selected_model = st.selectbox(
        "LLM Provider & Model",
        [
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
            "gpt-4o",
            "gpt-4o-mini",
            "claude-3-5-sonnet-20240620",
            "ollama/qwen2.5-coder:7b",
        ],
        index=0,
    )
    api_key_input = st.text_input("Custom API Key (Optional)", type="password", placeholder="Leave empty to use .env")
    
    threshold_choice = st.select_slider(
        "Minimum Severity Threshold",
        options=["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
        value="LOW",
    )
    enable_auto_fix = st.checkbox("Enable Auto-Fix Patch Generator", value=True)
    
    st.markdown("---")
    st.markdown("### 🤖 Active Swarm Agents")
    st.markdown("- **🛡️ SecOps Sentinel** (OWASP & Secrets)")
    st.markdown("- **🧹 Craftsman Critic** (Quality & Perf)")
    st.markdown("- **🧪 QA Sentinel** (Coverage & Regressions)")
    st.markdown("- **🛠️ Patch Surgeon** (Auto-Fixer)")
    st.markdown("- **🎯 Lead Architect** (Orchestrator)")

# Input Section
input_mode = st.radio(
    "Select Scan Target:",
    ["Paste Git Diff", "Sample Vulnerable Diff", "Full Local Repo / Folder", "GitHub PR URL"],
    horizontal=True,
)

SAMPLE_DIFF = """diff --git a/app/api/auth.py b/app/api/auth.py
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

diff_text = ""
pr_url = ""
repo_dir = ""

if input_mode == "Paste Git Diff":
    diff_text = st.text_area("Paste Unified Git Diff:", height=200, placeholder="diff --git a/file.py b/file.py...")
elif input_mode == "Sample Vulnerable Diff":
    diff_text = st.text_area("Sample Diff:", value=SAMPLE_DIFF, height=200)
elif input_mode == "Full Local Repo / Folder":
    repo_dir = st.text_input("Local Directory Path to Audit:", value=".", help="Absolute or relative path to project directory")
    max_scan_files = st.slider("Max files to scan:", min_value=5, max_value=100, value=30)
else:
    pr_url = st.text_input("GitHub Pull Request URL:", placeholder="https://github.com/octocat/Hello-World/pull/123")

run_button = st.button("🚀 Run Swarm Review", type="primary", use_container_width=True)

if run_button:
    # Update settings dynamically
    settings.llm_model = selected_model
    settings.severity_threshold = Severity(threshold_choice)
    settings.enable_auto_fix = enable_auto_fix

    llm_client = LLMClient(model=selected_model, api_key=api_key_input if api_key_input else None)
    git_provider = GitProvider()

    with st.spinner("🤖 Multi-agent swarm is auditing code..."):
        try:
            if pr_url:
                diff_ctx = git_provider.fetch_github_pr_diff(pr_url)
            elif repo_dir:
                from pr_sentinel.core.repo_scanner import RepoScanner
                diff_ctx = RepoScanner.scan_directory(directory_path=repo_dir, max_files=max_scan_files)
            else:
                diff_ctx = DiffParser.parse_diff(diff_text, pr_title="Interactive Web Diff")

            lead_agent = LeadReviewerAgent(llm_client=llm_client)
            report = lead_agent.review_pr(diff_ctx)

            # Metrics row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                verdict_color = {
                    PRVerdict.APPROVE: "green",
                    PRVerdict.COMMENT: "orange",
                    PRVerdict.REQUEST_CHANGES: "red",
                }.get(report.verdict, "blue")
                st.metric("Verdict", report.verdict.value)
            with col2:
                st.metric("Risk Score", f"{report.risk_score}/100")
            with col3:
                st.metric("Issues Found", report.total_issues)
            with col4:
                st.metric("Patches Generated", len(report.patches))

            # Tabs
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📋 Summary",
                "🔍 Detected Issues",
                "🛠️ Auto-Fix Patches",
                "🧪 Unit Tests",
                "🤖 Agent Discussion",
            ])

            with tab1:
                st.markdown("### Executive Summary")
                st.info(report.executive_summary)
                
                md_download = GitProvider.format_markdown_report(report)
                st.download_button(
                    label="📥 Download Review Markdown",
                    data=md_download,
                    file_name="pr_sentinel_review.md",
                    mime="text/markdown",
                )

            with tab2:
                if not report.issues:
                    st.success("✨ No issues detected under the current severity threshold!")
                else:
                    for i, issue in enumerate(report.issues, 1):
                        sev_badge = {
                            Severity.CRITICAL: "🚨 CRITICAL",
                            Severity.HIGH: "🔴 HIGH",
                            Severity.MEDIUM: "🟡 MEDIUM",
                            Severity.LOW: "🔵 LOW",
                            Severity.INFO: "ℹ️ INFO",
                        }.get(issue.severity, issue.severity.value)
                        
                        with st.expander(f"{i}. [{sev_badge}] {issue.title} ({issue.file_path}:{issue.line_start})", expanded=True):
                            st.write(f"**Category:** {issue.category.value} | **Audited By:** `{issue.agent_name}`")
                            if issue.cwe_id:
                                st.write(f"**CWE:** `{issue.cwe_id}`")
                            st.write(f"**Description:** {issue.description}")
                            st.write(f"**💡 Suggestion:** {issue.suggestion}")
                            if issue.code_snippet:
                                st.code(issue.code_snippet)

            with tab3:
                if not report.patches:
                    st.info("No auto-fix patches available.")
                else:
                    for j, patch in enumerate(report.patches, 1):
                        st.markdown(f"#### Patch #{j}: `{patch.file_path}` (Confidence: {int(patch.confidence_score*100)}%)")
                        st.caption(patch.rationale)
                        st.code(patch.unified_diff, language="diff")
                        st.download_button(
                            label=f"💾 Download Patch #{j} (.patch)",
                            data=patch.unified_diff,
                            file_name=f"fix_{j}.patch",
                            mime="text/plain",
                            key=f"patch_{j}",
                        )

            with tab4:
                if not report.generated_tests:
                    st.info("No regression tests proposed.")
                else:
                    for k, test in enumerate(report.generated_tests, 1):
                        st.markdown(f"#### Test File: `{test.test_file_path}` ({test.framework})")
                        st.caption(test.description)
                        st.code(test.test_code, language="python")

            with tab5:
                for agent_res in report.agent_results:
                    st.markdown(f"### {agent_res.agent_name} (*{agent_res.agent_role}*)")
                    st.markdown(f"> {agent_res.summary}")
                    st.write(f"- Issues detected: {len(agent_res.issues)}")
                    st.markdown("---")

        except Exception as e:
            st.error(f"Error executing swarm review: {e}")
