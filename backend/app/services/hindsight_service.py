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


class HindsightService:
    def __init__(self):
        self._client: Hindsight | None = None
        self._bank_id = settings.hindsight_bank_id

    def _get_client(self) -> Hindsight:
        if self._client is None:
            self._client = Hindsight(base_url=settings.hindsight_base_url)
        return self._client

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