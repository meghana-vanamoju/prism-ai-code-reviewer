import pytest
from unittest.mock import Mock, patch, AsyncMock

from app.models.memory import (
    RetainMemoryRequest,
    RecallMemoryRequest,
    ReflectMemoryRequest,
)
from app.services.hindsight_service import HindsightService


class TestHindsightService:
    @pytest.fixture
    def mock_client(self):
        with patch("app.services.hindsight_service.Hindsight") as mock:
            yield mock.return_value

    @pytest.fixture
    def service(self, mock_client):
        service = HindsightService()
        service._client = mock_client
        return service

    @pytest.mark.asyncio
    async def test_retain_memory_calls_hindsight(self, service, mock_client):
        mock_response = Mock()
        mock_response.success = True
        mock_response.bank_id = "prism-demo-team"
        mock_response.items_count = 1
        mock_response.var_async = False
        mock_client.aretain = AsyncMock(return_value=mock_response)

        request = RetainMemoryRequest(
            content="Test memory",
            context="Test context",
            metadata={"key": "value"},
        )

        response = await service.retain_memory(request)

        assert response.success is True
        assert response.bank_id == "prism-demo-team"
        assert response.items_count == 1
        mock_client.aretain.assert_awaited_once_with(
            bank_id="prism-demo-team",
            content="Test memory",
            context="Test context",
            metadata={"key": "value"},
            document_id=None,
        )

    @pytest.mark.asyncio
    async def test_recall_memories_calls_hindsight(self, service, mock_client):
        mock_result = Mock()
        mock_result.id = "mem-1"
        mock_result.text = "Financial calculations must use Decimal"
        mock_result.type = "observation"
        mock_result.context = "Team standard"
        mock_result.metadata = {"source": "team-standard"}
        mock_result.document_id = "doc-1"
        mock_client.arecall = AsyncMock(return_value=[mock_result])

        request = RecallMemoryRequest(
            query="What should we use for financial calculations?",
            budget="mid",
        )

        response = await service.recall_memories(request)

        assert response.query == "What should we use for financial calculations?"
        assert len(response.memories) == 1
        assert response.memories[0].text == "Financial calculations must use Decimal"
        mock_client.arecall.assert_awaited_once_with(
            bank_id="prism-demo-team",
            query="What should we use for financial calculations?",
            types=None,
            max_tokens=4096,
            budget="mid",
        )

    @pytest.mark.asyncio
    async def test_recall_memories_transforms_response(self, service, mock_client):
        mock_result = Mock()
        mock_result.id = "mem-1"
        mock_result.text = "Test memory text"
        mock_result.type = "experience"
        mock_result.context = "Test context"
        mock_result.metadata = {"key": "value"}
        mock_result.document_id = "doc-1"
        mock_client.arecall = AsyncMock(return_value=[mock_result])

        request = RecallMemoryRequest(query="test query")
        response = await service.recall_memories(request)

        assert isinstance(response, type(response))
        assert response.memories[0].id == "mem-1"
        assert response.memories[0].text == "Test memory text"
        assert response.memories[0].type == "experience"

    @pytest.mark.asyncio
    async def test_reflect_on_memories_calls_hindsight(self, service, mock_client):
        mock_fact = Mock()
        mock_fact.model_dump.return_value = {"text": "fact 1"}
        mock_response = Mock()
        mock_response.text = "Based on team standards, use Decimal for financial calculations."
        mock_response.based_on = [mock_fact]
        mock_client.areflect = AsyncMock(return_value=mock_response)

        request = ReflectMemoryRequest(
            query="What should I know about financial calculations?",
            budget="low",
        )

        response = await service.reflect_on_memories(request)

        assert response.query == "What should I know about financial calculations?"
        assert "Decimal" in response.answer
        assert response.based_on is not None
        mock_client.areflect.assert_awaited_once_with(
            bank_id="prism-demo-team",
            query="What should I know about financial calculations?",
            budget="low",
            context=None,
        )

    @pytest.mark.asyncio
    async def test_close_calls_client_close(self, service, mock_client):
        mock_client.close = AsyncMock()
        await service.close()
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retain_memory_accepts_retain_memory_request_from_raw_data(self, service, mock_client):
        """Regression test: verify seed script pattern works - constructing RetainMemoryRequest from raw dict."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.bank_id = "prism-demo-team"
        mock_response.items_count = 1
        mock_response.var_async = False
        mock_client.aretain = AsyncMock(return_value=mock_response)

        # This mimics the seed script pattern: raw dict -> RetainMemoryRequest -> retain_memory()
        raw_memory = {
            "content": "Financial calculations must use Decimal",
            "context": "Team coding standard",
            "metadata": {"source": "team-standard", "category": "financial"},
        }
        request = RetainMemoryRequest(**raw_memory)
        response = await service.retain_memory(request)

        assert response.success is True
        assert response.items_count == 1
        mock_client.aretain.assert_awaited_once_with(
            bank_id="prism-demo-team",
            content="Financial calculations must use Decimal",
            context="Team coding standard",
            metadata={"source": "team-standard", "category": "financial"},
            document_id=None,
        )