import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.main import app
from app.models.memory import (
    RetainMemoryResponse,
    RecallMemoryResponse,
    RecallMemoryItem,
    ReflectMemoryResponse,
)

client = TestClient(app)


class TestMemoryAPI:
    @patch("app.api.memory.hindsight_service")
    def test_retain_memory_endpoint(self, mock_service):
        mock_response = RetainMemoryResponse(
            success=True,
            bank_id="prism-demo-team",
            items_count=1,
            is_async=False,
        )
        mock_service.retain_memory = AsyncMock(return_value=mock_response)

        response = client.post(
            "/api/memory/retain",
            json={
                "content": "Financial calculations must use Decimal",
                "context": "Team standard",
                "metadata": {"source": "team-standard"},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["bank_id"] == "prism-demo-team"
        assert data["items_count"] == 1

    @patch("app.api.memory.hindsight_service")
    def test_retain_memory_validation_error(self, mock_service):
        response = client.post(
            "/api/memory/retain",
            json={"context": "Missing content"},
        )

        assert response.status_code == 422

    @patch("app.api.memory.hindsight_service")
    def test_recall_memories_endpoint(self, mock_service):
        mock_response = RecallMemoryResponse(
            query="What should we use for financial calculations?",
            memories=[
                RecallMemoryItem(
                    id="mem-1",
                    text="Financial calculations must use Decimal",
                    type="observation",
                    context="Team standard",
                    metadata={"source": "team-standard"},
                    document_id="doc-1",
                )
            ],
        )
        mock_service.recall_memories = AsyncMock(return_value=mock_response)

        response = client.post(
            "/api/memory/recall",
            json={
                "query": "What should we use for financial calculations?",
                "budget": "mid",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "What should we use for financial calculations?"
        assert len(data["memories"]) == 1
        assert "Decimal" in data["memories"][0]["text"]

    @patch("app.api.memory.hindsight_service")
    def test_recall_memories_validation_error(self, mock_service):
        response = client.post(
            "/api/memory/recall",
            json={"budget": "mid"},
        )

        assert response.status_code == 422

    @patch("app.api.memory.hindsight_service")
    def test_reflect_on_memories_endpoint(self, mock_service):
        mock_response = ReflectMemoryResponse(
            query="What should I know about financial calculations?",
            answer="Based on team standards, use Decimal for financial calculations.",
            based_on=[{"text": "Financial calculations must use Decimal"}],
        )
        mock_service.reflect_on_memories = AsyncMock(return_value=mock_response)

        response = client.post(
            "/api/memory/reflect",
            json={
                "query": "What should I know about financial calculations?",
                "budget": "low",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "What should I know about financial calculations?"
        assert "Decimal" in data["answer"]
        assert data["based_on"] is not None

    @patch("app.api.memory.hindsight_service")
    def test_reflect_validation_error(self, mock_service):
        response = client.post(
            "/api/memory/reflect",
            json={"budget": "low"},
        )

        assert response.status_code == 422

    @patch("app.api.memory.hindsight_service")
    def test_retain_memory_handles_exception(self, mock_service):
        mock_service.retain_memory = AsyncMock(side_effect=Exception("Hindsight connection failed"))

        response = client.post(
            "/api/memory/retain",
            json={"content": "Test memory"},
        )

        assert response.status_code == 500
        assert "Failed to retain memory" in response.json()["detail"]

    @patch("app.api.memory.hindsight_service")
    def test_recall_memories_handles_exception(self, mock_service):
        mock_service.recall_memories = AsyncMock(side_effect=Exception("Hindsight connection failed"))

        response = client.post(
            "/api/memory/recall",
            json={"query": "test query"},
        )

        assert response.status_code == 500
        assert "Failed to recall memories" in response.json()["detail"]

    @patch("app.api.memory.hindsight_service")
    def test_reflect_handles_exception(self, mock_service):
        mock_service.reflect_on_memories = AsyncMock(side_effect=Exception("Hindsight connection failed"))

        response = client.post(
            "/api/memory/reflect",
            json={"query": "test query"},
        )

        assert response.status_code == 500
        assert "Failed to reflect on memories" in response.json()["detail"]