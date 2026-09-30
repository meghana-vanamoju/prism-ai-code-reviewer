from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.review import Issue, MemoryUsed, RequirementsReport, Severity


class SourceMode(str, Enum):
    PASTE = "paste"
    FILES = "files"
    BRANCH = "branch"
    REQUIREMENTS = "requirements"


class JobStatus(str, Enum):
    QUEUED = "queued"
    FETCHING = "fetching"
    RECALLING = "recalling"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}


class SourceFile(BaseModel):
    path: str
    content: str = ""
    language: str = "other"
    size: int = 0


class DiffLine(BaseModel):
    type: str = Field(..., description="context | add | del")
    old_no: Optional[int] = None
    new_no: Optional[int] = None
    text: str


class DiffHunk(BaseModel):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    header: Optional[str] = None
    lines: List[DiffLine] = Field(default_factory=list)


class FileDiff(BaseModel):
    path: str
    old_path: Optional[str] = None
    status: str = "modified"
    hunks: List[DiffHunk] = Field(default_factory=list)

    @property
    def changed_lines(self) -> List[int]:
        lines: List[int] = []
        for hunk in self.hunks:
            for line in hunk.lines:
                if line.type in ("add", "del") and line.new_no is not None:
                    lines.append(line.new_no)
        return lines


class FileSummary(BaseModel):
    path: str
    language: str = "other"
    issue_count: int = 0
    skipped: bool = False
    skip_reason: Optional[str] = None
    content: Optional[str] = None
    truncated: bool = False


class SeverityCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    suggestion: int = 0


class ReviewResult(BaseModel):
    summary: str
    score: int
    severity_counts: SeverityCounts
    issues: List[Issue] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    files: List[FileSummary] = Field(default_factory=list)
    diffs: List[FileDiff] = Field(default_factory=list)
    memories_used: List[MemoryUsed] = Field(default_factory=list)
    requirements_report: Optional[RequirementsReport] = None
    model_used: str
    mode: SourceMode
    repo_url: Optional[str] = None
    branch: Optional[str] = None
    base_branch: Optional[str] = None


class JobProgress(BaseModel):
    step: str = "queued"
    current: int = 0
    total: int = 0
    current_file: Optional[str] = None


class JobRequest(BaseModel):
    mode: SourceMode = SourceMode.PASTE
    code: Optional[str] = Field(None, description="Pasted code (paste mode)")
    language: Optional[str] = None
    query: Optional[str] = None
    repo_url: Optional[str] = Field(None, description="Repository URL (branch mode)")
    branch: Optional[str] = Field(None, description="Branch name (branch mode)")
    base_branch: Optional[str] = Field(None, description="Base branch for diff (branch mode)")
    requirements: Optional[str] = Field(
        None,
        max_length=20_000,
        description="Requirements list to check the code against (requirements mode)",
    )
    bank_id: Optional[str] = None
    recall_budget: str = "mid"
    max_memories: int = Field(5, ge=1, le=20)


class SkippedFile(BaseModel):
    path: str
    reason: str


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: JobProgress
    result: Optional[ReviewResult] = None
    error: Optional[str] = None
    mode: SourceMode
    skipped: List[SkippedFile] = Field(default_factory=list)


class BranchInfo(BaseModel):
    name: str
    is_default: bool = False


class BranchListResponse(BaseModel):
    repo_url: str
    branches: List[BranchInfo] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    penalties: Dict[str, int] = Field(default_factory=dict)
    raw: int = 100
