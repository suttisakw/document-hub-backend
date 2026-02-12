from __future__ import annotations

import json
import re
from typing import Any

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"
REQUEST_TIMEOUT = (5, 120)


def _prompt(text: str) -> str:
    return (
        "Extract structured invoice data from the text below.\n"
        "Return JSON only.\n\n"
        "Fields:\n"
        "* invoice_number\n"
        "* date\n"
        "* vendor\n"
        "* total_amount\n\n"
        "TEXT:\n"
        f"{text}"
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
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


def extract_invoice_fields(text: str) -> dict[str, Any]:
    payload = {
        "model": MODEL_NAME,
        "prompt": _prompt(text),
        "stream": False,
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {
            "invoice_number": None,
            "date": None,
            "vendor": None,
            "total_amount": None,
            "_error": f"ollama_request_failed: {exc}",
        }

    body: dict[str, Any] = response.json() if response.content else {}
    model_text = str(body.get("response", "")).strip()

    parsed = _extract_json_object(model_text)
    if parsed is not None:
        return parsed

    return {
        "invoice_number": None,
        "date": None,
        "vendor": None,
        "total_amount": None,
        "_raw": model_text,
    }
