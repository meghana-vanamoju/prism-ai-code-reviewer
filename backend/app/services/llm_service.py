import json
from typing import Optional
from groq import AsyncGroq

from app.config import settings
from app.models.review import ReviewRequest, ReviewResponse, Issue, MemoryUsed, Severity


class LLMService:
    def __init__(self):
        self._client: Optional[AsyncGroq] = None

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY not configured")
            self._client = AsyncGroq(api_key=settings.groq_api_key)
        return self._client

    async def generate_review(
        self,
        request: ReviewRequest,
        memories: list[MemoryUsed],
    ) -> ReviewResponse:
        client = self._get_client()

        prompt = self._build_review_prompt(request, memories)

        try:
            response = await client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from LLM")

            return self._parse_review_response(content, memories)

        except Exception as e:
            raise RuntimeError(f"LLM review generation failed: {str(e)}")

    def _get_system_prompt(self) -> str:
        return """You are PRISM, an AI code review assistant with persistent memory of team standards and past decisions.
You review code by applying the team's historical knowledge, which is provided as memories.

Guidelines:
- Reference specific memories when they apply to issues you find
- Be specific and actionable in recommendations
- Use the severity levels: critical, high, medium, low, suggestion
- Only flag issues that are genuinely problematic or violate team standards
- If no issues found, return empty issues array and note that in summary
- Always output valid JSON matching the specified schema"""

    def _build_review_prompt(self, request: ReviewRequest, memories: list[MemoryUsed]) -> str:
        memories_text = ""
        if memories:
            memories_text = "\n\nRELEVANT TEAM MEMORIES (from Hindsight):\n"
            for i, mem in enumerate(memories, 1):
                memories_text += f"\n[{i}] {mem.text}"
                if mem.context:
                    memories_text += f" (Context: {mem.context})"
                if mem.metadata:
                    memories_text += f" [Metadata: {mem.metadata}]"

        query_text = f"\n\nSPECIFIC REVIEW FOCUS: {request.query}" if request.query else ""

        return f"""Review the following code:{memories_text}{query_text}

CODE TO REVIEW:
```{request.language or ''}
{request.code}
```

Return a JSON object with this exact structure:
{{
  "summary": "Brief overall assessment of the code",
  "issues": [
    {{
      "severity": "critical|high|medium|low|suggestion",
      "title": "Short issue title",
      "description": "Detailed explanation of the issue",
      "recommendation": "Specific fix or improvement",
      "memory_reference": "Reference to which memory informed this (e.g., '[1]' or 'Memory about Decimal usage')"
    }}
  ],
  "suggestions": ["General suggestions not tied to specific issues"],
  "memories_used": ["List of memory IDs or descriptions that were used"]
}}"""

    def _parse_review_response(self, content: str, memories: list[MemoryUsed]) -> ReviewResponse:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from LLM: {e}")

        issues = []
        for issue_data in data.get("issues", []):
            try:
                severity = Severity(issue_data.get("severity", "suggestion").lower())
            except ValueError:
                severity = Severity.SUGGESTION

            issues.append(Issue(
                severity=severity,
                title=issue_data.get("title", "Unknown issue"),
                description=issue_data.get("description", ""),
                recommendation=issue_data.get("recommendation", ""),
                memory_reference=issue_data.get("memory_reference"),
            ))

        memory_ids = data.get("memories_used", [])
        memories_used = []
        for mid in memory_ids:
            for mem in memories:
                if str(mem.id) in str(mid) or mid.lower() in mem.text.lower():
                    memories_used.append(mem)
                    break

        return ReviewResponse(
            summary=data.get("summary", "Code reviewed"),
            issues=issues,
            suggestions=data.get("suggestions", []),
            memories_used=memories_used,
            model_used=settings.groq_model,
        )


llm_service = LLMService()