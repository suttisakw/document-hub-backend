import json
import re
import httpx
from typing import Dict, Any, Optional

from app.providers.llm.base import LlmProvider, LlmResult
from app.services.circuit_breaker import CircuitBreaker

class OllamaProvider(LlmProvider):
    """Ollama implementation of the LLM provider."""

    def __init__(self, url: str, model_name: str, timeout: float = 120.0):
        self.url = url
        self.model_name = model_name
        self.timeout = httpx.Timeout(timeout, connect=10.0)
        self.circuit_breaker = CircuitBreaker(name=f"ollama_{model_name}", fail_threshold=3, recovery_timeout=60)

    def _prompt(self, text: str, schema_description: str) -> str:
        return (
            f"Extract structured data from the text below.\n"
            f"Return JSON only.\n\n"
            f"Schema/Fields:\n{schema_description}\n\n"
            f"TEXT:\n"
            f"{text}"
        )

    def _extract_json_object(self, text: str) -> Dict[str, Any] | None:
        text = text.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    async def _make_request(self, payload: dict) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.url, json=payload)
            response.raise_for_status()
            return response.json()

    async def extract_fields(self, text: str, schema_description: str) -> LlmResult:
        payload = {
            "model": self.model_name,
            "prompt": self._prompt(text, schema_description),
            "stream": False,
        }

        try:
            body = await self.circuit_breaker.call(self._make_request, payload)
            model_text = str(body.get("response", "")).strip()
            parsed = self._extract_json_object(model_text) or {}
            
            return LlmResult(
                data=parsed,
                raw_response=model_text,
                model_name=self.model_name
            )
        except Exception as exc:
            return LlmResult(
                data={"_error": str(exc)},
                raw_response="",
                model_name=self.model_name
            )

    async def classify_document(self, text: str, categories: list[str]) -> str:
        prompt = (
            f"Classify the following document text into exactly one of these categories: {', '.join(categories)}.\n"
            f"Respond with only the category name.\n\n"
            f"TEXT:\n{text[:4000]}"
        )
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(self.url, json=payload)
                response.raise_for_status()
                body = response.json()
                result = str(body.get("response", "")).strip().lower()
                # Find matching category
                for cat in categories:
                    if cat.lower() in result:
                        return cat
                return categories[0] # Fallback
            except Exception:
                return categories[0]

    def get_name(self) -> str:
        return f"ollama_{self.model_name}"

    async def get_embedding(self, text: str) -> list[float]:
        """Generate vector embedding using Ollama."""
        # Ollama embedding endpoint is typically /api/embeddings or /api/embed
        endpoint = self.url.replace("/api/generate", "/api/embeddings") 
        if "/api/embeddings" not in endpoint:
            # Fallback for manually specified URLs without /api/generate
            endpoint = f"{self.url.rstrip('/')}/api/embeddings"

        payload = {
            "model": self.model_name,
            "prompt": text[:2000]  # Limit context for embeddings
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                body = response.json()
                return body.get("embedding") or []
            except Exception as e:
                logger.error(f"Ollama embedding failed: {e}")
                return []
