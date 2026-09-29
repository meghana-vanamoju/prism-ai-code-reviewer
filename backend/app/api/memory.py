from fastapi import APIRouter, HTTPException, status

from app.models.memory import (
    RetainMemoryRequest,
    RetainMemoryResponse,
    RecallMemoryRequest,
    RecallMemoryResponse,
    ReflectMemoryRequest,
    ReflectMemoryResponse,
)
from app.services.hindsight_service import hindsight_service

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.post("/retain", response_model=RetainMemoryResponse, status_code=status.HTTP_201_CREATED)
async def retain_memory(request: RetainMemoryRequest):
    try:
        return await hindsight_service.retain_memory(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retain memory: {str(e)}",
        )


@router.post("/recall", response_model=RecallMemoryResponse)
async def recall_memories(request: RecallMemoryRequest):
    try:
        return await hindsight_service.recall_memories(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to recall memories: {str(e)}",
        )


@router.post("/reflect", response_model=ReflectMemoryResponse)
async def reflect_on_memories(request: ReflectMemoryRequest):
    try:
        return await hindsight_service.reflect_on_memories(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reflect on memories: {str(e)}",
        )