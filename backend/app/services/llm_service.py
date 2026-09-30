import asyncio
import json
import random
import re
import time
from typing import Optional, Sequence

from groq import AsyncGroq

from app.config import settings
from app.models.job import SourceFile
from app.models.review import (
    FileReview,
    Issue,
    MemoryUsed,
    RequirementItem,
    RequirementStatus,
    RequirementsReport,
    ReviewRequest,
    ReviewResponse,
    Severity,
)

# Keep prompts small: the free-tier TPM budget is 8k tokens/minute org-wide,
# so a multi-file review must fit in a handful of requests per minute.
CONTENT_CHAR_LIMIT = 6_000
FILE_PROMPT_MEMORIES = 3
MAX_LLM_ATTEMPTS = 4
REQUIREMENTS_CHAR_LIMIT = 8_000
REQUIREMENTS_CODE_LIMIT = 24_000
REQUIREMENTS_MAX_ITEMS = 40
REQUIREMENTS_KINDS = {"feature", "bug", "task", "issue", "story", "other"}
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}


def _is_retryable(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    if status in _RETRYABLE_STATUS_CODES:
        return True
    text = str(error)
    # The model occasionally returns an empty/non-JSON body (HTTP 400 with
    # `json_validate_failed`); that is transient generation noise, not a
    # permanent request error.
    if status == 400 and "json_validate_failed" in text:
        return True
    if isinstance(error, ValueError) and (
        "Empty response" in text or "Invalid JSON" in text
    ):
        return True
    return False


def _retry_delay(error: Exception, attempt: int) -> float:
    match = re.search(r"try again in ([\d.]+)", str(error))
    if match:
        return min(float(match.group(1)) + random.uniform(0.5, 1.5), 60.0)
    return min(5 * (2 ** (attempt - 1)) + random.uniform(0, 2), 60.0)


def _coerce_line(value) -> Optional[int]:
    try:
        line = int(value)
    except (TypeError, ValueError):
        return None
    return line if line >= 1 else None


def _empty_to_none(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class LLMService:
    def __init__(self):
        self._client: Optional[AsyncGroq] = None
        # Serializes API calls and paces them against the org TPM budget so
        # concurrent file reviews don't fight each other over 429s.
        self._api_lock = asyncio.Lock()
        self._next_slot = 0.0

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY not configured")
            self._client = AsyncGroq(api_key=settings.groq_api_key)
        return self._client

    def _token_estimate(self, system: str, user: str) -> int:
        return (len(system) + len(user)) // 4 + 512

    async def _paced_create(self, *, system: str, user: str):
        """One chat completion, serialized and paced to the TPM budget."""
        async with self._api_lock:
            while True:
                now = time.monotonic()
                if now >= self._next_slot:
                    break
                await asyncio.sleep(self._next_slot - now)
            try:
                response = await self._get_client().chat.completions.create(
                    model=settings.groq_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.1,
                    max_tokens=2048,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                if getattr(e, "status_code", None) == 429:
                    self._next_slot = time.monotonic() + _retry_delay(e, 1)
                raise
            usage = getattr(response, "usage", None)
            tokens = int(getattr(usage, "total_tokens", 0) or 0)
            if not tokens:
                tokens = self._token_estimate(system, user)
            limit = max(settings.groq_tpm_limit, 1)
            self._next_slot = time.monotonic() + (tokens / limit) * 60.0 + 0.25
            return response

    async def _create_and_parse(self, *, system: str, user: str, parse):
        """Call the LLM with retry/backoff, then parse the JSON payload."""
        last_error: Exception = RuntimeError("LLM call failed")
        for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
            try:
                response = await self._paced_create(system=system, user=user)
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response from LLM")
                return parse(content)
            except Exception as e:
                last_error = e
                if not _is_retryable(e) or attempt == MAX_LLM_ATTEMPTS:
                    break
                await asyncio.sleep(_retry_delay(e, attempt))
        raise last_error

    async def generate_review(
        self,
        request: ReviewRequest,
        memories: list[MemoryUsed],
    ) -> ReviewResponse:
        prompt = self._build_review_prompt(request, memories)

        try:
            return await self._create_and_parse(
                system=self._get_system_prompt(),
                user=prompt,
                parse=lambda raw: self._parse_review_response(raw, memories),
            )
        except Exception as e:
            raise RuntimeError(f"LLM review generation failed: {str(e)}")

    async def generate_file_review(
        self,
        *,
        path: str,
        content: str,
        language: str,
        memories: list[MemoryUsed],
        focus: Optional[str] = None,
        is_diff: bool = False,
    ) -> FileReview:
        """Review a single file (full source) or a single-file diff, with line numbers."""
        prompt = self._build_file_prompt(
            path=path,
            content=content,
            language=language,
            memories=memories,
            focus=focus,
            is_diff=is_diff,
        )

        try:
            return await self._create_and_parse(
                system=self._get_file_system_prompt(),
                user=prompt,
                parse=lambda raw: self._parse_file_review(raw, path=path),
            )
        except Exception as e:
            raise RuntimeError(f"LLM file review failed: {str(e)}")

    async def generate_requirements_report(
        self,
        *,
        requirements: str,
        files: Sequence[SourceFile],
        memories: list[MemoryUsed],
    ) -> RequirementsReport:
        """Check each requirement against the provided code and report coverage."""
        prompt = self._build_requirements_prompt(
            requirements=requirements, files=files, memories=memories
        )

        try:
            return await self._create_and_parse(
                system=self._get_requirements_system_prompt(),
                user=prompt,
                parse=self._parse_requirements_report,
            )
        except Exception as e:
            raise RuntimeError(f"LLM requirements review failed: {str(e)}")

    def _get_requirements_system_prompt(self) -> str:
        return """You are PRISM, an AI code review assistant checking whether a codebase implements a list of requirements (issues, features, work items, user stories, bug fixes).

Guidelines:
- Map every requirement to concrete code evidence (file path, plus line number when possible)
- status is "implemented" only when the code clearly fulfils the requirement, "partial" when only part of it is covered, "missing" when you find no supporting code
- kind is one of: feature, bug, task, issue, story, other
- For partial/missing items, gaps states exactly what is absent; for implemented items gaps is an empty string
- Never invent files or line numbers that are not in the provided code
- If there are more requirements than can be answered reliably, cover the first ones and stop (do not emit filler items)
- Always output valid JSON matching the requested structure"""

    def _build_requirements_prompt(
        self,
        *,
        requirements: str,
        files: Sequence[SourceFile],
        memories: list[MemoryUsed],
    ) -> str:
        parts: list[str] = []

        if memories:
            parts.append("RELEVANT TEAM MEMORIES (from Hindsight):")
            for i, mem in enumerate(memories[:FILE_PROMPT_MEMORIES], 1):
                line = f"[{i}] {mem.text}"
                if mem.context:
                    line += f" (Context: {mem.context})"
                parts.append(line)
            parts.append("")

        req = requirements
        req_truncated = len(req) > REQUIREMENTS_CHAR_LIMIT
        if req_truncated:
            req = req[:REQUIREMENTS_CHAR_LIMIT] + "\n... [truncated]"
        parts.append("REQUIREMENTS TO CHECK (prefer one requirement per line):")
        parts.append("```")
        parts.append(req)
        parts.append("```")
        if req_truncated:
            parts.append("(Requirements were truncated; only check what is shown.)")
        parts.append("")

        parts.append("CODEBASE UNDER REVIEW:")
        budget = REQUIREMENTS_CODE_LIMIT
        omitted: list[str] = []
        for source_file in files:
            header = f"--- FILE: {source_file.path} ({source_file.language}) ---"
            if budget - len(header) < 64:
                omitted.append(source_file.path)
                continue
            body = source_file.content or ""
            room = budget - len(header)
            if len(body) > room:
                body = body[:room] + "\n... [truncated]"
            numbered = "\n".join(
                f"{i:5}| {line}" for i, line in enumerate(body.splitlines(), 1)
            )
            parts.append(header)
            parts.append(numbered)
            budget -= len(header) + len(numbered) + 2

        if omitted:
            parts.append(
                f"(Omitted {len(omitted)} file(s) due to size limits: "
                + ", ".join(omitted[:20])
                + ")"
            )
        parts.append("")

        parts.append(
            f"""
Return a JSON object with this exact structure:
{{
  "summary": "One-sentence coverage overview",
  "items": [
    {{
      "id": "R1",
      "title": "Short requirement title (reuse the original id, e.g. '#12' or 'US-3', when the requirement has one)",
      "kind": "feature|bug|task|issue|story|other",
      "status": "implemented|partial|missing",
      "evidence": ["path/to/file.py:12"],
      "gaps": "What is missing or incomplete (empty string if implemented)",
      "notes": "Optional extra context (or empty string)"
    }}
  ]
}}

Emit at most {REQUIREMENTS_MAX_ITEMS} items, covering the requirements in order."""
        )
        return "\n".join(parts)

    def _parse_requirements_report(self, content: str) -> RequirementsReport:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from LLM: {e}")

        raw_items = data.get("items", []) or []
        if not isinstance(raw_items, list):
            raw_items = []

        items: list[RequirementItem] = []
        for index, item_data in enumerate(raw_items[:REQUIREMENTS_MAX_ITEMS]):
            if not isinstance(item_data, dict):
                continue

            raw_status = str(item_data.get("status", "")).strip().lower()
            try:
                status = RequirementStatus(raw_status)
            except ValueError:
                status = RequirementStatus.PARTIAL

            kind = str(item_data.get("kind", "")).strip().lower()
            if kind not in REQUIREMENTS_KINDS:
                kind = "other"

            raw_evidence = item_data.get("evidence") or []
            if isinstance(raw_evidence, str):
                raw_evidence = [raw_evidence]
            if not isinstance(raw_evidence, list):
                raw_evidence = []
            evidence = [str(e)[:200] for e in raw_evidence if str(e).strip()][:8]

            items.append(
                RequirementItem(
                    id=str(item_data.get("id") or f"R{index + 1}"),
                    title=str(item_data.get("title") or "Untitled requirement"),
                    kind=kind,
                    status=status,
                    evidence=evidence,
                    gaps=str(item_data.get("gaps") or ""),
                    notes=_empty_to_none(item_data.get("notes")),
                )
            )

        implemented = sum(1 for i in items if i.status == RequirementStatus.IMPLEMENTED)
        partial = sum(1 for i in items if i.status == RequirementStatus.PARTIAL)
        missing = sum(1 for i in items if i.status == RequirementStatus.MISSING)
        total = len(items)

        return RequirementsReport(
            items=items,
            summary=str(data.get("summary") or ""),
            implemented=implemented,
            partial=partial,
            missing=missing,
            coverage_pct=round(100 * implemented / total) if total else 0,
        )

    def _get_file_system_prompt(self) -> str:
        return """You are PRISM, an AI code review assistant with persistent memory of team standards and past decisions.

Guidelines:
- Review ONLY the file/diff provided; be specific and actionable
- Every issue must carry an accurate 1-based `line` number from the code shown (for diffs: the new-file / right-hand numbering)
- Use severity levels: critical, high, medium, low, suggestion
- Reference team memories with `memory_reference` when they apply (e.g. "[1]")
- Only flag genuinely problematic code; if none, return an empty issues array
- Always output valid JSON matching the requested structure"""

    def _build_file_prompt(
        self,
        *,
        path: str,
        content: str,
        language: str,
        memories: list[MemoryUsed],
        focus: Optional[str],
        is_diff: bool,
    ) -> str:
        parts: list[str] = []

        if memories:
            parts.append("RELEVANT TEAM MEMORIES (from Hindsight):")
            for i, mem in enumerate(memories[:FILE_PROMPT_MEMORIES], 1):
                line = f"[{i}] {mem.text}"
                if mem.context:
                    line += f" (Context: {mem.context})"
                parts.append(line)
            parts.append("")

        if focus:
            parts.append(f"SPECIFIC REVIEW FOCUS: {focus}")
            parts.append("")

        truncated = len(content) > CONTENT_CHAR_LIMIT
        if truncated:
            content = content[:CONTENT_CHAR_LIMIT] + "\n... [truncated]"

        if is_diff:
            parts.append(f"UNIFIED DIFF FOR: {path}")
            parts.append("Line numbers in issues must use the NEW file numbering (+ and context lines).")
            parts.append("```diff")
            parts.append(content)
            parts.append("```")
        else:
            numbered = "\n".join(
                f"{i:5}| {line}" for i, line in enumerate(content.splitlines(), 1)
            )
            parts.append(f"FILE: {path} ({language})")
            parts.append("```")
            parts.append(numbered)
            parts.append("```")

        parts.append(
            """
Return a JSON object with this exact structure:
{
  "summary": "One-sentence assessment of this file",
  "issues": [
    {
      "severity": "critical|high|medium|low|suggestion",
      "title": "Short issue title",
      "description": "Detailed explanation",
      "recommendation": "Specific fix or improvement",
      "line": 12,
      "end_line": 14,
      "memory_reference": "Reference to a memory, e.g. '[1]' (or empty string)"
    }
  ],
  "suggestions": ["General improvements not tied to a line"]
}"""
        )
        if truncated:
            parts.append("(Note: content was truncated; only review what is shown.)")
        return "\n".join(parts)

    def _parse_file_review(self, content: str, *, path: str) -> FileReview:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from LLM: {e}")

        issues: list[Issue] = []
        for issue_data in data.get("issues", []) or []:
            if not isinstance(issue_data, dict):
                continue
            try:
                severity = Severity(str(issue_data.get("severity", "suggestion")).lower())
            except ValueError:
                severity = Severity.SUGGESTION

            line = _coerce_line(issue_data.get("line"))
            end_line = _coerce_line(issue_data.get("end_line"))
            if line is not None and end_line is not None and end_line < line:
                end_line = line

            issues.append(
                Issue(
                    severity=severity,
                    title=str(issue_data.get("title") or "Unknown issue"),
                    description=str(issue_data.get("description") or ""),
                    recommendation=str(issue_data.get("recommendation") or ""),
                    memory_reference=_empty_to_none(issue_data.get("memory_reference")),
                    file=path,
                    line=line,
                    end_line=end_line,
                )
            )

        suggestions = [str(s) for s in data.get("suggestions", []) or [] if isinstance(s, (str, int, float))]
        return FileReview(
            summary=str(data.get("summary") or ""),
            issues=issues,
            suggestions=suggestions,
        )

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