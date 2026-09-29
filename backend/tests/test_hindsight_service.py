import pytest
from unittest.mock import Mock, patch, AsyncMock

from app.config import settings
from app.models.memory import (
    RetainMemoryRequest,
    RecallMemoryRequest,
    ReflectMemoryRequest,
)
from app.services.hindsight_service import HindsightService


@pytest.fixture
def mock_client():
    with patch("app.services.hindsight_service.Hindsight") as mock:
        yield mock.return_value


@pytest.fixture
def service(mock_client):
    service = HindsightService()
    service._client = mock_client
    return service


class TestHindsightService:
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


class TestHindsightBankConfiguration:
    """The bank's retain extraction mode decides whether retention needs the
    Hindsight server's LLM. These tests pin the behaviour that keeps feedback
    retention working when that LLM is unreachable."""

    @pytest.fixture
    def mock_httpx(self):
        with patch("app.services.hindsight_service.httpx.AsyncClient") as mock:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = None
            mock.return_value = client
            yield client

    @staticmethod
    def _response(status_code: int = 200):
        response = Mock()
        response.status_code = status_code
        response.raise_for_status = Mock()
        return response

    @pytest.mark.asyncio
    async def test_patches_retain_extraction_mode(self, service, mock_httpx):
        mock_httpx.patch.return_value = self._response()

        await service.ensure_bank_configuration()

        mock_httpx.patch.assert_awaited_once_with(
            "http://localhost:8888/v1/default/banks/prism-demo-team/config",
            json={"updates": {"retain_extraction_mode": "chunks"}},
        )
        mock_httpx.put.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_bank_when_missing_then_patches(self, service, mock_httpx):
        mock_httpx.patch.side_effect = [self._response(404), self._response(200)]
        mock_httpx.put.return_value = self._response()

        await service.ensure_bank_configuration()

        mock_httpx.put.assert_awaited_once_with(
            "http://localhost:8888/v1/default/banks/prism-demo-team",
            json={"bank_id": "prism-demo-team", "retain_extraction_mode": "chunks"},
        )
        assert mock_httpx.patch.await_count == 2

    @pytest.mark.asyncio
    async def test_failure_does_not_raise(self, service, mock_httpx):
        mock_httpx.patch.side_effect = RuntimeError("connection refused")

        await service.ensure_bank_configuration()

    @pytest.mark.asyncio
    async def test_http_error_does_not_raise(self, service, mock_httpx):
        response = self._response()
        response.raise_for_status.side_effect = RuntimeError("HTTP 500")
        mock_httpx.patch.return_value = response

        await service.ensure_bank_configuration()

    @pytest.mark.asyncio
    async def test_no_request_when_mode_is_empty(self, service, mock_httpx):
        with patch.object(settings, "hindsight_retain_extraction_mode", ""):
            await service.ensure_bank_configuration()

        mock_httpx.patch.assert_not_called()
        mock_httpx.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_retain_memory_waits_for_persistence(self, service, mock_client):
        """Retention stays synchronous so recalled memories are never
        submitted-but-not-yet-stored."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.bank_id = "prism-demo-team"
        mock_response.items_count = 1
        mock_response.var_async = False
        mock_client.aretain = AsyncMock(return_value=mock_response)

        response = await service.retain_memory(
            RetainMemoryRequest(content="Feedback record", context="Code review feedback")
        )

        assert response.is_async is False
        mock_client.aretain_batch.assert_not_called()
