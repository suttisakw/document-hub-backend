from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ExternalOcrResult:
    external_job_id: str | None
    raw: dict


async def trigger_external_ocr(
    *,
    url: str,
    api_key: str,
    filepath: str,
    interface_id: str,
    transaction_id: str,
) -> ExternalOcrResult:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = {
        "filepath": filepath,
        "interface_id": interface_id,
        "transaction_id": transaction_id,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=data, headers=headers)
        resp.raise_for_status()
        payload = resp.json()

    # Some implementations return request_id instead of job_id
    ext_id = payload.get("job_id")
    if ext_id is None and payload.get("request_id") is not None:
        ext_id = str(payload.get("request_id"))

    return ExternalOcrResult(external_job_id=ext_id, raw=payload)
