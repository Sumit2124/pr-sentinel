import os
import glob
from typing import List, Optional, Set
from pr_sentinel.core.models import DiffContext, FileDiff, DiffHunk, ChangeType
from pr_sentinel.core.ast_analyzer import ASTAnalyzer

DEFAULT_IGNORED_DIRS: Set[str] = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "eggs",
    ".eggs",
    ".mypy_cache",
    ".idea",
    ".vscode",
}

SUPPORTED_EXTENSIONS: Set[str] = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".sql",
    ".sh",
    ".yaml",
    ".yml",
    ".json",
    ".dockerfile",
    "Dockerfile",
}


class RepoScanner:
    """Recursively scans an entire repository directory and converts code files into structured review contexts."""

    @staticmethod
    def scan_directory(
        directory_path: str = ".",
        max_files: int = 50,
        file_types: Optional[List[str]] = None,
    ) -> DiffContext:
        root_path = os.path.abspath(directory_path)
        files_to_review: List[FileDiff] = []
        total_lines = 0

        target_exts = set(file_types) if file_types else SUPPORTED_EXTENSIONS

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune ignored directories in-place
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORED_DIRS and not d.startswith(".")]

            for fname in sorted(filenames):
                if len(files_to_review) >= max_files:
                    break

                _, ext = os.path.splitext(fname)
                if ext not in target_exts and fname not in target_exts:
                    continue

                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, root_path)

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception:
                    continue

                lines = content.splitlines()
                if not lines:
                    continue

                total_lines += len(lines)

                # Construct a pseudo-hunk representing the entire file content for agent review
                hunk_lines = [f"+{line}" for line in lines]
                hunk = DiffHunk(
                    old_start=0,
                    old_length=0,
                    new_start=1,
                    new_length=len(lines),
                    lines=hunk_lines,
                    section_header=f"File: {rel_path}",
                )

                pseudo_diff = f"--- /dev/null\n+++ b/{rel_path}\n@@ -0,0 +1,{len(lines)} @@\n" + "\n".join(hunk_lines)

                files_to_review.append(
                    FileDiff(
                        source_file=rel_path,
                        target_file=rel_path,
                        change_type=ChangeType.ADDED,
                        is_binary=False,
                        added_lines=len(lines),
                        deleted_lines=0,
                        hunks=[hunk],
                        raw_diff=pseudo_diff,
                    )
                )

        return DiffContext(
            files=files_to_review,
            total_added=total_lines,
            total_deleted=0,
            raw_diff="\n\n".join([f.raw_diff for f in files_to_review]),
            branch_name="FULL_REPO_AUDIT",
            pr_title=f"Full Codebase Security & Architecture Audit ({os.path.basename(root_path)})",
            pr_description=f"Automated full-repo scan containing {len(files_to_review)} source files and {total_lines} lines of code.",
        )
