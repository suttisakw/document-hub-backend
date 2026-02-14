from __future__ import annotations

import json
import re
from typing import Any

import json
import re
from typing import Any

import os
from app.providers.llm.base import LlmProvider, LlmResult
from app.providers.llm.ollama_provider import OllamaProvider
from app.providers.llm.openai_provider import OpenAiProvider

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

def get_llm_provider() -> LlmProvider:
    """Get the configured LLM provider based on environment variables."""
    if OPENAI_API_KEY:
        return OpenAiProvider(api_key=OPENAI_API_KEY, model_name=OPENAI_MODEL)
    return OllamaProvider(url=OLLAMA_URL, model_name=OLLAMA_MODEL)

async def extract_invoice_fields(text: str) -> dict[str, Any]:
    """
    Extract invoice fields using the configured LLM provider.
    """
    schema = (
        "* invoice_number\n"
        "* date\n"
        "* vendor\n"
        "* total_amount"
    )
    provider = get_llm_provider()
    result = await provider.extract_fields(text, schema)
    
    # Ensure backward compatibility of returned keys if needed
    data = result.data
    if "_error" in data:
        return {
            "invoice_number": None,
            "date": None,
            "vendor": None,
            "total_amount": None,
            "_error": data["_error"]
        }
    
    return data

async def extract_fields_custom(text: str, schema: str) -> LlmResult:
    """Extract fields with custom schema."""
    provider = get_llm_provider()
    return await provider.extract_fields(text, schema)
