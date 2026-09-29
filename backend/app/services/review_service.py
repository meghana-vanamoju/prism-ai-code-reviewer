from typing import Optional
from app.config import settings
from app.services.hindsight_service import hindsight_service
from app.services.llm_service import llm_service
from app.models.memory import RecallMemoryRequest, RetainMemoryRequest
from app.models.review import ReviewRequest, ReviewResponse, MemoryUsed, IssueFeedback, IssueDecision


class ReviewService:
    async def review_code(self, request: ReviewRequest) -> ReviewResponse:
        recall_request = RecallMemoryRequest(
            query=request.query or self._build_recall_query(request.code),
            bank_id=request.bank_id or settings.hindsight_bank_id,
            budget=request.recall_budget,
            max_tokens=4096,
        )

        recall_response = await hindsight_service.recall_memories(recall_request)

        memories = [
            MemoryUsed(
                id=m.id,
                text=m.text,
                type=m.type,
                context=m.context,
                metadata=m.metadata,
            )
            for m in recall_response.memories[:request.max_memories]
        ]

        review_response = await llm_service.generate_review(request, memories)
        review_response.memories_used = memories
        return review_response

    def _build_recall_query(self, code: str) -> str:
        return f"code review standards and best practices for: {code[:200]}"

    async def store_review_feedback(
        self,
        code: str,
        review_summary: str,
        issues: list,
        issue_feedback: list[IssueFeedback],
        feedback: Optional[str] = None,
        bank_id: Optional[str] = None,
    ):
        target_bank = bank_id or settings.hindsight_bank_id

        # Build structured memory content
        memory_lines = [
            "Code Review Feedback Record",
            f"Code snippet: {code[:200]}...",
            f"Review summary: {review_summary}",
            f"Total issues found: {len(issues)}",
        ]

        # Add per-issue feedback
        if issue_feedback:
            memory_lines.append("\nIssue decisions:")
            for fb in issue_feedback:
                memory_lines.append(
                    f"  - {fb.issue_title}: {fb.decision.value}"
                    + (f" (Reason: {fb.reason})" if fb.reason else "")
                )

        # Add general feedback
        if feedback:
            memory_lines.append(f"\nGeneral feedback: {feedback}")

        # Add metadata about the review topic for better recall
        topics = []
        for issue in issues:
            if issue.memory_reference:
                topics.append(issue.memory_reference)
        if topics:
            memory_lines.append(f"\nRelated memories: {', '.join(topics)}")

        memory_content = "\n".join(memory_lines)

        request = RetainMemoryRequest(
            content=memory_content,
            context="Code review feedback",
            metadata={
                "source": "review-feedback",
                "type": "feedback",
                "review_topic": review_summary[:100],
                "issues_count": str(len(issues)),
                "accepted_count": str(sum(1 for fb in issue_feedback if fb.decision == IssueDecision.ACCEPTED)),
                "rejected_count": str(sum(1 for fb in issue_feedback if fb.decision == IssueDecision.REJECTED)),
            },
        )

        await hindsight_service.retain_memory(request)


review_service = ReviewService()