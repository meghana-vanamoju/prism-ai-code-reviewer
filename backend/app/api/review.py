from fastapi import APIRouter, HTTPException, status

from app.models.review import (
    ReviewRequest,
    ReviewResponse,
    ReviewFeedbackRequest,
    ReviewFeedbackResponse,
)
from app.services.review_service import review_service

router = APIRouter(prefix="/api/review", tags=["review"])


@router.post("", response_model=ReviewResponse, status_code=status.HTTP_200_OK)
async def review_code(request: ReviewRequest):
    try:
        return await review_service.review_code(request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review failed: {str(e)}",
        )


@router.post("/feedback", response_model=ReviewFeedbackResponse, status_code=status.HTTP_201_CREATED)
async def review_feedback(request: ReviewFeedbackRequest):
    try:
        await review_service.store_review_feedback(
            code=request.code,
            review_summary=request.review_summary,
            issues=request.issues,
            issue_feedback=request.issue_feedback,
            feedback=request.feedback,
            bank_id=request.bank_id,
        )
        return ReviewFeedbackResponse(success=True, message="Feedback stored in Hindsight")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store feedback: {str(e)}",
        )