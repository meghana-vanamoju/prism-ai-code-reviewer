import pytest
from unittest.mock import Mock, patch, AsyncMock

from app.models.review import ReviewRequest, ReviewResponse, Issue, MemoryUsed, Severity, IssueFeedback, IssueDecision
from app.services.review_service import ReviewService
from app.models.memory import RecallMemoryResponse, RecallMemoryItem


class TestReviewService:
    @pytest.fixture
    def mock_hindsight_service(self):
        with patch("app.services.review_service.hindsight_service") as mock:
            yield mock

    @pytest.fixture
    def mock_llm_service(self):
        with patch("app.services.review_service.llm_service") as mock:
            yield mock

    @pytest.fixture
    def review_service(self, mock_hindsight_service, mock_llm_service):
        return ReviewService()

    @pytest.mark.asyncio
    async def test_review_code_recalls_memories_and_generates_review(self, review_service, mock_hindsight_service, mock_llm_service):
        mock_recall_response = RecallMemoryResponse(
            query="financial calculations",
            memories=[
                RecallMemoryItem(
                    id="mem-1",
                    text="Financial calculations must use Decimal rather than floating-point arithmetic.",
                    type="observation",
                    context="Team standard",
                    metadata={"source": "team-standard"},
                    document_id="doc-1",
                )
            ],
        )
        mock_hindsight_service.recall_memories = AsyncMock(return_value=mock_recall_response)

        mock_review_response = ReviewResponse(
            summary="Code uses float for monetary calculations",
            issues=[
                Issue(
                    severity=Severity.HIGH,
                    title="Floating-point for monetary values",
                    description="Using float for price calculations causes precision issues",
                    recommendation="Use Decimal type for monetary values",
                    memory_reference="[1] Financial calculations must use Decimal",
                )
            ],
            suggestions=["Consider using the existing money utility"],
            memories_used=[
                MemoryUsed(
                    id="mem-1",
                    text="Financial calculations must use Decimal rather than floating-point arithmetic.",
                    type="observation",
                    context="Team standard",
                    metadata={"source": "team-standard"},
                )
            ],
            model_used="openai/gpt-oss-20b",
        )
        mock_llm_service.generate_review = AsyncMock(return_value=mock_review_response)

        request = ReviewRequest(
            code="function calculateTotal(items) { let total = 0; for (const item of items) { total += item.price; } return total; }",
            language="javascript",
            query="Review for financial calculation issues",
        )

        response = await review_service.review_code(request)

        assert response.summary == "Code uses float for monetary calculations"
        assert len(response.issues) == 1
        assert response.issues[0].severity == Severity.HIGH
        assert "Decimal" in response.issues[0].recommendation
        assert len(response.memories_used) == 1
        assert response.memories_used[0].id == "mem-1"

        mock_hindsight_service.recall_memories.assert_awaited_once()
        mock_llm_service.generate_review.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_review_code_uses_actual_hindsight_memories_in_response_not_llm_strings(self, review_service, mock_hindsight_service, mock_llm_service):
        """Regression test: memories_used must come from actual Hindsight recall, not LLM string references."""
        mock_recall_response = RecallMemoryResponse(
            query="financial calculations",
            memories=[
                RecallMemoryItem(
                    id="mem-1",
                    text="Financial calculations must use Decimal rather than floating-point arithmetic.",
                    type="observation",
                    context="Team standard",
                    metadata={"source": "team-standard"},
                    document_id="doc-1",
                ),
                RecallMemoryItem(
                    id="mem-2",
                    text="Always validate user input before processing.",
                    type="rule",
                    context="Security guideline",
                    metadata={"source": "security-policy"},
                    document_id="doc-2",
                ),
            ],
        )
        mock_hindsight_service.recall_memories = AsyncMock(return_value=mock_recall_response)

        # Simulate real LLM behavior: the _parse_review_response returns empty memories_used
        # because the matching logic fails to match "[1]" strings to actual memories
        mock_review_response = ReviewResponse(
            summary="Code uses float for monetary calculations",
            issues=[
                Issue(
                    severity=Severity.HIGH,
                    title="Floating-point for monetary values",
                    description="Using float for price calculations causes precision issues",
                    recommendation="Use Decimal type for monetary values",
                    memory_reference="[1]",
                ),
                Issue(
                    severity=Severity.MEDIUM,
                    title="Missing input validation",
                    description="User input not validated",
                    recommendation="Add validation",
                    memory_reference="[2]",
                ),
            ],
            suggestions=["Consider using the existing money utility"],
            # LLM's _parse_review_response currently returns empty list due to broken matching
            memories_used=[],
            model_used="openai/gpt-oss-20b",
        )
        mock_llm_service.generate_review = AsyncMock(return_value=mock_review_response)

        request = ReviewRequest(
            code="function calculateTotal(items) { let total = 0; for (const item of items) { total += item.price; } return total; }",
            language="javascript",
            query="Review for financial calculation issues",
            max_memories=5,
        )

        response = await review_service.review_code(request)

        # The fix ensures memories_used contains actual MemoryUsed objects from Hindsight
        assert len(response.memories_used) == 2
        assert response.memories_used[0].id == "mem-1"
        assert response.memories_used[0].text == "Financial calculations must use Decimal rather than floating-point arithmetic."
        assert response.memories_used[0].type == "observation"
        assert response.memories_used[0].context == "Team standard"
        assert response.memories_used[0].metadata == {"source": "team-standard"}

        assert response.memories_used[1].id == "mem-2"
        assert response.memories_used[1].text == "Always validate user input before processing."
        assert response.memories_used[1].type == "rule"
        assert response.memories_used[1].context == "Security guideline"
        assert response.memories_used[1].metadata == {"source": "security-policy"}

        # Verify memory_reference in issues is preserved
        assert response.issues[0].memory_reference == "[1]"
        assert response.issues[1].memory_reference == "[2]"

        mock_hindsight_service.recall_memories.assert_awaited_once()
        mock_llm_service.generate_review.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_review_code_with_no_memories(self, review_service, mock_hindsight_service, mock_llm_service):
        mock_hindsight_service.recall_memories = AsyncMock(return_value=RecallMemoryResponse(
            query="test",
            memories=[],
        ))

        mock_llm_service.generate_review = AsyncMock(return_value=ReviewResponse(
            summary="No issues found",
            issues=[],
            suggestions=[],
            memories_used=[],
            model_used="openai/gpt-oss-20b",
        ))

        request = ReviewRequest(code="console.log('hello')", language="javascript")
        response = await review_service.review_code(request)

        assert response.summary == "No issues found"
        assert len(response.issues) == 0
        assert len(response.memories_used) == 0

    def test_build_recall_query(self, review_service):
        code = "function calculate(x, y) { return x + y; }"
        query = review_service._build_recall_query(code)
        assert "code review standards" in query.lower()
        assert "calculate" in query

    @pytest.mark.asyncio
    async def test_store_review_feedback_accepted(self, review_service, mock_hindsight_service):
        from app.models.review import Issue

        issues = [
            Issue(severity=Severity.HIGH, title="Float precision", description="Using float", recommendation="Use Decimal"),
        ]
        issue_feedback = [
            IssueFeedback(issue_title="Float precision", decision=IssueDecision.ACCEPTED, reason="Team standard requires Decimal"),
        ]

        mock_hindsight_service.retain_memory = AsyncMock()

        await review_service.store_review_feedback(
            code="function calc() { return 1.1 + 2.2; }",
            review_summary="Found float precision issue",
            issues=issues,
            issue_feedback=issue_feedback,
            feedback="Agreed, will fix",
        )

        mock_hindsight_service.retain_memory.assert_awaited_once()
        call_args = mock_hindsight_service.retain_memory.call_args[0][0]
        assert "Float precision: accepted" in call_args.content
        assert "Reason: Team standard requires Decimal" in call_args.content
        assert "General feedback: Agreed, will fix" in call_args.content
        assert call_args.metadata["source"] == "review-feedback"
        assert call_args.metadata["accepted_count"] == "1"
        assert call_args.metadata["rejected_count"] == "0"

    @pytest.mark.asyncio
    async def test_store_review_feedback_rejected(self, review_service, mock_hindsight_service):
        from app.models.review import Issue

        issues = [
            Issue(severity=Severity.LOW, title="Naming style", description="Use camelCase", recommendation="Rename variables"),
        ]
        issue_feedback = [
            IssueFeedback(issue_title="Naming style", decision=IssueDecision.REJECTED, reason="Project uses snake_case"),
        ]

        mock_hindsight_service.retain_memory = AsyncMock()

        await review_service.store_review_feedback(
            code="function calc() { return 1; }",
            review_summary="Style suggestions",
            issues=issues,
            issue_feedback=issue_feedback,
            feedback=None,
        )

        mock_hindsight_service.retain_memory.assert_awaited_once()
        call_args = mock_hindsight_service.retain_memory.call_args[0][0]
        assert "Naming style: rejected" in call_args.content
        assert "Reason: Project uses snake_case" in call_args.content
        assert call_args.metadata["accepted_count"] == "0"
        assert call_args.metadata["rejected_count"] == "1"

    @pytest.mark.asyncio
    async def test_store_review_feedback_mixed_decisions(self, review_service, mock_hindsight_service):
        from app.models.review import Issue

        issues = [
            Issue(severity=Severity.HIGH, title="Security issue", description="SQL injection", recommendation="Use params"),
            Issue(severity=Severity.LOW, title="Style issue", description="Line too long", recommendation="Break lines"),
        ]
        issue_feedback = [
            IssueFeedback(issue_title="Security issue", decision=IssueDecision.ACCEPTED, reason="Critical vulnerability"),
            IssueFeedback(issue_title="Style issue", decision=IssueDecision.REJECTED, reason="Auto-formatter handles this"),
        ]

        mock_hindsight_service.retain_memory = AsyncMock()

        await review_service.store_review_feedback(
            code="query = f'SELECT * FROM users WHERE id={user_id}'",
            review_summary="Security and style issues",
            issues=issues,
            issue_feedback=issue_feedback,
            feedback="Will fix security, ignore style",
        )

        mock_hindsight_service.retain_memory.assert_awaited_once()
        call_args = mock_hindsight_service.retain_memory.call_args[0][0]
        assert "Security issue: accepted" in call_args.content
        assert "Style issue: rejected" in call_args.content
        assert call_args.metadata["accepted_count"] == "1"
        assert call_args.metadata["rejected_count"] == "1"