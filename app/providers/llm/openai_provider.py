import json
import logging
from typing import Any, Dict, List, Optional
import httpx
from app.providers.llm.base import LlmProvider, LlmResult

logger = logging.getLogger(__name__)

class OpenAiProvider(LlmProvider):
    """OpenAI implementation using official API."""
    
    def __init__(self, api_key: str, model_name: str = "gpt-4o"):
        self.api_key = api_key
        self.model_name = model_name
        self.api_url = "https://api.openai.com/v1/chat/completions"

    async def extract_fields(self, text: str, schema: str) -> LlmResult:
        """Extract fields using OpenAI Chat Completions with JSON mode."""
        prompt = (
            f"You are a document extraction expert. Extract the following fields from the text: \n{schema}\n\n"
            f"TEXT TO EXTRACT:\n{text}\n\n"
            "Respond ONLY with a valid JSON object matching the requested fields."
        )
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that extracts structured data in JSON format."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
                response.raise_for_status()
                
                result_data = response.json()
                content = result_data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                
                return LlmResult(
                    data=parsed,
                    raw_response=content,
                    provider="openai",
                    model=self.model_name
                )
        except Exception as e:
            logger.error(f"OpenAI extraction failed: {e}")
            return LlmResult(
                data={"_error": str(e)},
                raw_response="",
                provider="openai",
                model=self.model_name
            )

    async def classify_document(self, text: str, categories: List[str]) -> str:
        """Classify document using OpenAI."""
        prompt = (
            f"Classify the following document text into exactly one of these categories: {', '.join(categories)}.\n"
            "Analyze the content carefully. Respond with ONLY the category name.\n\n"
            f"TEXT:\n{text[:4000]}"
        )
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are a precise document classifier. Respond only with the category name."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
                response.raise_for_status()
                
                content = response.json()["choices"][0]["message"]["content"].strip()
                
                # Exact match first
                for cat in categories:
                    if cat.lower() == content.lower():
                        return cat
                
                # Partial match fallback
                for cat in categories:
                    if cat.lower() in content.lower():
                        return cat
                
                return categories[0]
        except Exception as e:
            logger.error(f"OpenAI classification failed: {e}")
            return categories[0]

    async def get_embedding(self, text: str) -> List[float]:
        """Generate embeddings using OpenAI text-embedding-3-small."""
        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Consistent embedding model regardless of chat model
        embedding_model = "text-embedding-3-small"
        
        payload = {
            "input": text[:8000], # Max tokens handling needed in real app
            "model": embedding_model
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            return []

    def get_name(self) -> str:
        return "openai"
