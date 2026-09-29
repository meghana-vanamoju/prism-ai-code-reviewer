import logging

import httpx
from hindsight_client import Hindsight
from hindsight_client_api.models import RetainResponse, RecallResult, ReflectResponse

from app.config import settings
from app.models.memory import (
    RetainMemoryRequest,
    RetainMemoryResponse,
    RecallMemoryRequest,
    RecallMemoryItem,
    RecallMemoryResponse,
    ReflectMemoryRequest,
    ReflectMemoryResponse,
)

logger = logging.getLogger(__name__)


class HindsightService:
    def __init__(self):
        self._client: Hindsight | None = None
        self._bank_id = settings.hindsight_bank_id

    def _get_client(self) -> Hindsight:
        if self._client is None:
            self._client = Hindsight(base_url=settings.hindsight_base_url)
        return self._client

    async def ensure_bank_configuration(self) -> None:
        """Align the bank with the configured retain extraction mode.

        Hindsight's default "concise" extraction mode asks the Hindsight
        server to summarise every chunk into atomic facts using the LLM it was
        started with. When that server cannot reach its LLM provider the
        summarisation fails and every retain request fails, even though the
        database and recall paths are healthy.

        The "chunks" mode stores the submitted content directly, so retention
        no longer depends on that LLM call while the content stays recallable
        through the normal semantic recall path.
        """
        mode = settings.hindsight_retain_extraction_mode
        if not mode:
            return

        base_url = settings.hindsight_base_url.rstrip("/")
        config_url = f"{base_url}/v1/default/banks/{self._bank_id}/config"
        bank_url = f"{base_url}/v1/default/banks/{self._bank_id}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.patch(
                    config_url, json={"updates": {"retain_extraction_mode": mode}}
                )
                if response.status_code == 404:
                    await client.put(bank_url, json={"bank_id": self._bank_id, "retain_extraction_mode": mode})
                    response = await client.patch(
                        config_url, json={"updates": {"retain_extraction_mode": mode}}
                    )
                response.raise_for_status()
        except Exception as exc:
            logger.warning(
                "Could not set retain_extraction_mode=%s on Hindsight bank %s: %s",
                mode,
                self._bank_id,
                exc,
            )
            return

        logger.info("Hindsight bank %s retain_extraction_mode set to %s", self._bank_id, mode)

    async def retain_memory(self, request: RetainMemoryRequest) -> RetainMemoryResponse:
        client = self._get_client()
        response: RetainResponse = await client.aretain(
            bank_id=self._bank_id,
            content=request.content,
            context=request.context,
            metadata=request.metadata,
            document_id=request.document_id,
        )
        return RetainMemoryResponse(
            success=response.success,
            bank_id=response.bank_id,
            items_count=response.items_count,
            is_async=response.var_async,
        )

    async def recall_memories(self, request: RecallMemoryRequest) -> RecallMemoryResponse:
        client = self._get_client()
        bank_id = request.bank_id or self._bank_id
        results: list[RecallResult] = await client.arecall(
            bank_id=bank_id,
            query=request.query,
            types=request.types,
            max_tokens=request.max_tokens,
            budget=request.budget,
        )
        memories = [
            RecallMemoryItem(
                id=r.id,
                text=r.text,
                type=r.type,
                context=r.context,
                metadata=r.metadata,
                document_id=r.document_id,
            )
            for r in results
        ]
        return RecallMemoryResponse(query=request.query, memories=memories)

    async def reflect_on_memories(self, request: ReflectMemoryRequest) -> ReflectMemoryResponse:
        client = self._get_client()
        bank_id = request.bank_id or self._bank_id
        response: ReflectResponse = await client.areflect(
            bank_id=bank_id,
            query=request.query,
            budget=request.budget,
            context=request.context,
        )
        based_on = None
        if response.based_on:
            based_on = [fact.model_dump() for fact in response.based_on]
        return ReflectMemoryResponse(
            query=request.query,
            answer=response.text,
            based_on=based_on,
        )

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None


hindsight_service = HindsightService()