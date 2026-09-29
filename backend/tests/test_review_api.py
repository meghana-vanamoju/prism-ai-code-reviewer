import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.main import app
from app.models.review import ReviewResponse, Issue, MemoryUsed, Severity, ReviewFeedbackResponse, IssueFeedback, IssueDecision

client = TestClient(app)


class TestReviewAPI:
    @patch("app.api.review.review_service")
    def test_review_code_endpoint(self, mock_review_service):
        mock_response = ReviewResponse(
            summary="Code uses float for monetary values",
            issues=[
                Issue(
                    severity=Severity.HIGH,
                    title="Floating-point precision",
                    description="Using float for prices causes precision issues",
                    recommendation="Use Decimal type",
                    memory_reference="[1] Team standard for Decimal",
                )
            ],
            suggestions=["Use money utility"],
            memories_used=[
                MemoryUsed(
                    id="mem-1",
                    text="Financial calculations must use Decimal",
                    type="observation",
                    context="Team standard",
                    metadata={"source": "team-standard"},
                )
            ],
            model_used="openai/gpt-oss-20b",
        )
        mock_review_service.review_code = AsyncMock(return_value=mock_response)

        response = client.post(
            "/api/review",
            json={
                "code": "function calculateTotal(items) { let total = 0; for (const item of items) { total += item.price; } return total; }",
                "language": "javascript",
                "query": "Check for financial issues",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["summary"] == "Code uses float for monetary values"
        assert len(data["issues"]) == 1
        assert data["issues"][0]["severity"] == "high"
        assert "Decimal" in data["issues"][0]["recommendation"]
        assert len(data["memories_used"]) == 1
        assert data["memories_used"][0]["id"] == "mem-1"
        assert data["model_used"] == "openai/gpt-oss-20b"

    @patch("app.api.review.review_service")
    def test_review_code_minimal_request(self, mock_review_service):
        mock_response = ReviewResponse(
            summary="No issues",
            issues=[],
            suggestions=[],
            memories_used=[],
            model_used="openai/gpt-oss-20b",
        )
        mock_review_service.review_code = AsyncMock(return_value=mock_response)

        response = client.post(
            "/api/review",
            json={"code": "console.log('hello')"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["summary"] == "No issues"

    def test_review_code_validation_error(self):
        response = client.post("/api/review", json={})
        assert response.status_code == 422

    def test_review_code_missing_code(self):
        response = client.post("/api/review", json={"language": "python"})
        assert response.status_code == 422

    @patch("app.api.review.review_service")
    def test_review_code_handles_exception(self, mock_review_service):
        mock_review_service.review_code = AsyncMock(side_effect=RuntimeError("LLM failed"))

        response = client.post(
            "/api/review",
            json={"code": "test code"},
        )

        assert response.status_code == 500
        assert "LLM failed" in response.json()["detail"]

    @patch("app.api.review.review_service")
    def test_review_feedback_endpoint_accepted(self, mock_review_service):
        mock_review_service.store_review_feedback = AsyncMock()

        response = client.post(
            "/api/review/feedback",
            json={
                "code": "function calc() { return 1.1 + 2.2; }",
                "review_summary": "Found float precision issue",
                "issues": [
                    {"severity": "high", "title": "Float precision", "description": "Using float", "recommendation": "Use Decimal"}
                ],
                "issue_feedback": [
                    {"issue_title": "Float precision", "decision": "accepted", "reason": "Team standard requires Decimal"}
                ],
                "feedback": "Agreed, will fix",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "Feedback stored" in data["message"]

        mock_review_service.store_review_feedback.assert_awaited_once()

    @patch("app.api.review.review_service")
    def test_review_feedback_endpoint_rejected(self, mock_review_service):
        mock_review_service.store_review_feedback = AsyncMock()

        response = client.post(
            "/api/review/feedback",
            json={
                "code": "function calc() { return 1; }",
                "review_summary": "Style suggestions",
                "issues": [
                    {"severity": "low", "title": "Naming style", "description": "Use camelCase", "recommendation": "Rename variables"}
                ],
                "issue_feedback": [
                    {"issue_title": "Naming style", "decision": "rejected", "reason": "Project uses snake_case"}
                ],
                "feedback": None,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True

        mock_review_service.store_review_feedback.assert_awaited_once()

    def test_review_feedback_validation_error(self):
        response = client.post("/api/review/feedback", json={})
        assert response.status_code == 422

    @patch("app.api.review.review_service")
    def test_review_feedback_handles_exception(self, mock_review_service):
        mock_review_service.store_review_feedback = AsyncMock(side_effect=Exception("Hindsight failed"))

        response = client.post(
            "/api/review/feedback",
            json={
                "code": "test",
                "review_summary": "test",
                "issues": [],
                "issue_feedback": [],
            },
        )

        assert response.status_code == 500
        assert "Failed to store feedback" in response.json()["detail"]