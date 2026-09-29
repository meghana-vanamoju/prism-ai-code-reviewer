from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SUGGESTION = "suggestion"


class Issue(BaseModel):
    severity: Severity
    title: str
    description: str
    recommendation: str
    memory_reference: Optional[str] = None


class MemoryUsed(BaseModel):
    id: str
    text: str
    type: Optional[str] = None
    context: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ReviewRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Code or diff to review")
    language: Optional[str] = Field(None, description="Programming language")
    query: Optional[str] = Field(None, description="Optional specific review question")
    bank_id: Optional[str] = Field(None, description="Optional bank ID (uses default if not provided)")
    recall_budget: str = Field("mid", description="Hindsight recall budget: low, mid, high")
    max_memories: int = Field(5, description="Maximum memories to include in review")


class ReviewResponse(BaseModel):
    summary: str
    issues: List[Issue]
    suggestions: List[str]
    memories_used: List[MemoryUsed]
    model_used: str


class IssueDecision(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class IssueFeedback(BaseModel):
    issue_title: str
    decision: IssueDecision
    reason: Optional[str] = None


class ReviewFeedbackRequest(BaseModel):
    review_id: Optional[str] = None
    code: str
    review_summary: str
    issues: List[Issue]
    issue_feedback: List[IssueFeedback] = Field(default_factory=list)
    feedback: Optional[str] = None
    bank_id: Optional[str] = None


class ReviewFeedbackResponse(BaseModel):
    success: bool
    message: str