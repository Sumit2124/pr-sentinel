from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from pr_sentinel.config import Severity


class ChangeType(str, Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"


class DiffHunk(BaseModel):
    old_start: int
    old_length: int
    new_start: int
    new_length: int
    lines: List[str]
    section_header: str = ""


class FileDiff(BaseModel):
    source_file: str
    target_file: str
    change_type: ChangeType
    is_binary: bool = False
    added_lines: int = 0
    deleted_lines: int = 0
    hunks: List[DiffHunk] = Field(default_factory=list)
    raw_diff: str = ""


class DiffContext(BaseModel):
    files: List[FileDiff] = Field(default_factory=list)
    total_added: int = 0
    total_deleted: int = 0
    raw_diff: str = ""
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    pr_title: Optional[str] = None
    pr_description: Optional[str] = None


class IssueCategory(str, Enum):
    SECURITY = "SECURITY"
    CODE_QUALITY = "CODE_QUALITY"
    PERFORMANCE = "PERFORMANCE"
    BUG_RISK = "BUG_RISK"
    TEST_COVERAGE = "TEST_COVERAGE"
    STYLE = "STYLE"


class CodeIssue(BaseModel):
    id: Optional[str] = None
    file_path: str
    line_start: int
    line_end: Optional[int] = None
    severity: Severity = Severity.MEDIUM
    category: IssueCategory = IssueCategory.CODE_QUALITY
    agent_name: str
    title: str
    description: str
    suggestion: str
    code_snippet: Optional[str] = None
    cwe_id: Optional[str] = None  # E.g. CWE-89 (SQL Injection)


class SuggestedPatch(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    original_code: str
    fixed_code: str
    unified_diff: str
    rationale: str
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.9)


class GeneratedTest(BaseModel):
    target_file: str
    test_file_path: str
    framework: str = "pytest"
    test_code: str
    description: str
    covers_issue_title: Optional[str] = None


class AgentReviewResult(BaseModel):
    agent_name: str
    agent_role: str
    status: str = "SUCCESS"
    summary: str
    issues: List[CodeIssue] = Field(default_factory=list)
    patches: List[SuggestedPatch] = Field(default_factory=list)
    generated_tests: List[GeneratedTest] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PRVerdict(str, Enum):
    APPROVE = "APPROVE"
    COMMENT = "COMMENT"
    REQUEST_CHANGES = "REQUEST_CHANGES"


class PRReviewReport(BaseModel):
    title: str = "PR Sentinel Review"
    target_ref: Optional[str] = None
    risk_score: int = Field(ge=0, le=100, description="Risk score from 0 (Safe) to 100 (Critical)")
    verdict: PRVerdict
    executive_summary: str
    total_issues: int = 0
    issues: List[CodeIssue] = Field(default_factory=list)
    patches: List[SuggestedPatch] = Field(default_factory=list)
    generated_tests: List[GeneratedTest] = Field(default_factory=list)
    agent_results: List[AgentReviewResult] = Field(default_factory=list)
