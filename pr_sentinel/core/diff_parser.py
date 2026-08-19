import re
from typing import List, Optional
from pr_sentinel.core.models import DiffContext, FileDiff, DiffHunk, ChangeType

try:
    from unidiff import PatchSet, PatchedFile
    HAS_UNIDIFF = True
except ImportError:
    HAS_UNIDIFF = False
    PatchSet = None
    PatchedFile = None


class DiffParser:
    """Parses raw unified git diffs into structured Pydantic models."""

    @staticmethod
    def parse_diff(raw_diff_text: str, branch_name: Optional[str] = None, pr_title: Optional[str] = None) -> DiffContext:
        if not raw_diff_text or not raw_diff_text.strip():
            return DiffContext(files=[], total_added=0, total_deleted=0, raw_diff="", branch_name=branch_name, pr_title=pr_title)

        if HAS_UNIDIFF:
            try:
                return DiffParser._parse_with_unidiff(raw_diff_text, branch_name, pr_title)
            except Exception:
                return DiffParser._parse_fallback(raw_diff_text, branch_name, pr_title)
        else:
            return DiffParser._parse_fallback(raw_diff_text, branch_name, pr_title)

    @staticmethod
    def _parse_with_unidiff(raw_diff_text: str, branch_name: Optional[str], pr_title: Optional[str]) -> DiffContext:
        patch_set = PatchSet(raw_diff_text)
        files: List[FileDiff] = []
        total_added = 0
        total_deleted = 0

        for patched_file in patch_set:
            source = patched_file.source_file.replace("a/", "", 1) if patched_file.source_file.startswith("a/") else patched_file.source_file
            target = patched_file.target_file.replace("b/", "", 1) if patched_file.target_file.startswith("b/") else patched_file.target_file

            if patched_file.is_added_file:
                change_type = ChangeType.ADDED
            elif patched_file.is_removed_file:
                change_type = ChangeType.DELETED
            elif patched_file.is_rename:
                change_type = ChangeType.RENAMED
            else:
                change_type = ChangeType.MODIFIED

            file_added = patched_file.added
            file_deleted = patched_file.removed
            total_added += file_added
            total_deleted += file_deleted

            hunks: List[DiffHunk] = []
            for hunk in patched_file:
                hunk_lines = [str(line).rstrip("\r\n") for line in hunk]
                hunks.append(
                    DiffHunk(
                        old_start=hunk.source_start,
                        old_length=hunk.source_length,
                        new_start=hunk.target_start,
                        new_length=hunk.target_length,
                        lines=hunk_lines,
                        section_header=hunk.section_header or "",
                    )
                )

            files.append(
                FileDiff(
                    source_file=source,
                    target_file=target,
                    change_type=change_type,
                    is_binary=patched_file.is_binary_file,
                    added_lines=file_added,
                    deleted_lines=file_deleted,
                    hunks=hunks,
                    raw_diff=str(patched_file),
                )
            )

        return DiffContext(
            files=files,
            total_added=total_added,
            total_deleted=total_deleted,
            raw_diff=raw_diff_text,
            branch_name=branch_name,
            pr_title=pr_title,
        )

    @staticmethod
    def _parse_fallback(raw_diff_text: str, branch_name: Optional[str], pr_title: Optional[str]) -> DiffContext:
        files: List[FileDiff] = []
        total_added = 0
        total_deleted = 0

        # Split diff by "diff --git"
        file_chunks = re.split(r"(?=diff --git )", raw_diff_text)

        for chunk in file_chunks:
            if not chunk.strip():
                continue

            # Extract filenames
            match = re.search(r"diff --git a/(.*?) b/(.*)", chunk)
            if match:
                source = match.group(1).strip()
                target = match.group(2).strip()
            else:
                source = "unknown"
                target = "unknown"

            change_type = ChangeType.MODIFIED
            if "new file mode" in chunk:
                change_type = ChangeType.ADDED
            elif "deleted file mode" in chunk:
                change_type = ChangeType.DELETED

            added = len(re.findall(r"^\+[^+]", chunk, re.MULTILINE))
            deleted = len(re.findall(r"^-[^-]", chunk, re.MULTILINE))
            total_added += added
            total_deleted += deleted

            # Extract hunks
            hunks: List[DiffHunk] = []
            hunk_matches = list(re.finditer(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", chunk))
            for i, hmatch in enumerate(hunk_matches):
                old_start = int(hmatch.group(1))
                old_len = int(hmatch.group(2)) if hmatch.group(2) else 1
                new_start = int(hmatch.group(3))
                new_len = int(hmatch.group(4)) if hmatch.group(4) else 1
                header = hmatch.group(5).strip()

                start_idx = hmatch.end()
                end_idx = hunk_matches[i + 1].start() if i + 1 < len(hunk_matches) else len(chunk)
                hunk_body = chunk[start_idx:end_idx]
                lines = [l for l in hunk_body.splitlines() if l.startswith(("+", "-", " "))]

                hunks.append(
                    DiffHunk(
                        old_start=old_start,
                        old_length=old_len,
                        new_start=new_start,
                        new_length=new_len,
                        lines=lines,
                        section_header=header,
                    )
                )

            files.append(
                FileDiff(
                    source_file=source,
                    target_file=target,
                    change_type=change_type,
                    is_binary=False,
                    added_lines=added,
                    deleted_lines=deleted,
                    hunks=hunks,
                    raw_diff=chunk,
                )
            )

        return DiffContext(
            files=files,
            total_added=total_added,
            total_deleted=total_deleted,
            raw_diff=raw_diff_text,
            branch_name=branch_name,
            pr_title=pr_title,
        )
