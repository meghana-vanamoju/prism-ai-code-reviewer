from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class RetainMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Memory content to store")
    context: Optional[str] = Field(None, description="Optional context description")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")
    document_id: Optional[str] = Field(None, description="Optional document ID for grouping")


class RetainMemoryResponse(BaseModel):
    success: bool
    bank_id: str
    items_count: int
    is_async: bool


class RecallMemoryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    bank_id: Optional[str] = Field(None, description="Optional bank ID (uses default if not provided)")
    types: Optional[List[str]] = Field(None, description="Optional fact types to filter")
    budget: str = Field("mid", description="Budget level: low, mid, high")
    max_tokens: int = Field(4096, description="Maximum tokens in results")


class RecallMemoryItem(BaseModel):
    id: str
    text: str
    type: Optional[str] = None
    context: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    document_id: Optional[str] = None


class RecallMemoryResponse(BaseModel):
    query: str
    memories: List[RecallMemoryItem]


class ReflectMemoryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Question or prompt")
    bank_id: Optional[str] = Field(None, description="Optional bank ID")
    budget: str = Field("low", description="Budget level: low, mid, high")
    context: Optional[str] = Field(None, description="Optional additional context")


class ReflectMemoryResponse(BaseModel):
    query: str
    answer: str
    based_on: Optional[List[Dict[str, Any]]] = None


class HealthCheckResponse(BaseModel):
    status: str
    service: str