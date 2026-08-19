# 🚀 PR-Sentinel: Complete Setup & Deployment Guide

This guide documents the exact step-by-step process for:
1. **Local Setup with Ollama** (100% Free, Private Local LLM)
2. **GitHub Deployment & CI/CD Gatekeeper Setup** (Autonomous PR Reviewer Bot)
3. **Using AI Agent Rectification Plans** (Cursor / Claude Code / Copilot / Aider)

---

## 🦙 PART 1: Local Setup with Ollama (100% Offline & Private)

### Step 1: Install Ollama & Pull the Model
1. Download and install Ollama from [ollama.com](https://ollama.com) (or `brew install ollama`).
2. Pull the coding LLM judge:
   ```bash
   # Recommended coding model (7B parameters):
   ollama run qwen2.5-coder:7b

   # OR for lightweight laptops (< 8GB RAM):
   # ollama run qwen2.5-coder:1.5b
   ```

### Step 2: Configure Environment
In the repository directory (`/Users/sumit/Documents/AI PROJECTS/pr-sentinel`):
1. Copy the environment file:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` to set:
   ```ini
   LLM_MODEL=ollama/qwen2.5-coder:7b
   OLLAMA_API_BASE=http://localhost:11434
   ```

### Step 3: Install & Launch
```bash
# 1. Activate virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. Launch interactive Web UI
streamlit run pr_sentinel/web/app.py

# 3. Or run terminal showcase demo
pr-sentinel sample
```

---

## 🐙 PART 2: GitHub Repository & Automated PR Bot Setup

### Step 1: Push Code to Your GitHub
1. Create a new empty repository on GitHub named `pr-sentinel` (do not check initialize with README).
2. Push your local repository:
   ```bash
   cd "/Users/sumit/Documents/AI PROJECTS/pr-sentinel"
   git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/pr-sentinel.git
   git push -u origin main
   ```

---

### Step 2: Configure GitHub Workflow Permissions
1. In your GitHub repository, click **Settings** ➔ **Actions** (left sidebar) ➔ **General**.
2. Under **Workflow permissions**:
   - Select: **Read and write permissions** ✅
   - Check: **Allow GitHub Actions to create and approve pull requests** ✅
3. Click **Save**.

---

### Step 3: Add Cloud API Secret for GitHub Actions
Since GitHub Actions runs in GitHub's cloud runners:
1. Go to **Settings** ➔ **Secrets and variables** ➔ **Actions**.
2. Click **New repository secret**:
   - **Name**: `GEMINI_API_KEY` (or `OPENAI_API_KEY`)
   - **Secret**: *(Paste your API key)*
3. Click **Add secret**.

*(Note: `GITHUB_TOKEN` is automatically provided by GitHub Actions for free).*

---

### Step 4: Enable Strict Merge Gatekeeper (Branch Protection)
To block PRs from merging when PR-Sentinel detects critical vulnerabilities:
1. Go to **Settings** ➔ **Branches** ➔ Click **Add branch protection rule**.
2. **Branch name pattern**: `main` (or `master` / `integration`).
3. Check: **Require status checks to pass before merging** ✅.
4. Search and check: **`PR-Sentinel Security & Quality Gatekeeper`**.
5. Click **Create / Save changes**.

---

## 🧪 PART 3: How to Test the Bot on GitHub

1. Create a test branch and push a deliberate flaw:
   ```bash
   git checkout -b test-pr
   # Edit any file, then commit and push:
   git commit -am "test: introduce test endpoint"
   git push -u origin test-pr
   ```
2. Open a Pull Request on GitHub into `main`.
3. **PR-Sentinel will automatically**:
   - Audit the diff with SecOps, Quality, and QA agents.
   - Post a detailed Markdown report with CWE security flaws, code snippets, and fix patches.
   - Fail the status check (**RED 🔴 - Merge Blocked**) if vulnerabilities are present.
4. **Auto-Fix Command**:
   - Reply in the PR comments with:
     ```
     /sentinel fix
     ```
   - The bot will auto-apply all recommended patches, commit them directly to `test-pr`, and turn the check **GREEN 🟢 (Ready to Merge)**!

---

## 🤖 PART 4: AI Agent Rectification Prompt Pack

Every time PR-Sentinel reviews a PR or scans a repository, it generates an AI-ready prompt file: **`agent_rectification.md`**.

### How to use with Cursor, Claude Code, Copilot Workspace, or Aider:
1. Download `agent_rectification.md` from the PR Artifacts or Streamlit Web UI.
2. Feed the file directly to your AI coding assistant.
3. The AI agent will read the exact line numbers, security root causes, unified diffs, and verification checklist to automatically rectify your codebase!

---

## 💻 CLI Quick Reference

```bash
# Review local unstaged changes
pr-sentinel review

# Review staged changes with strict gate exit code
pr-sentinel review --staged --strict-gate

# Scan a remote GitHub repo and branch
pr-sentinel scan --repo https://github.com/owner/repo --branch main --output audit.md

# Scan a local codebase folder
pr-sentinel scan /path/to/project --max-files 40

# Interactively apply generated fix patches
pr-sentinel fix
```
