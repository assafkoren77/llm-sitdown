"""Anthropic provider implementation."""

import asyncio
import logging
import httpx
from typing import List, Dict, Any
from .base import LLMProvider
from ..settings import get_settings

logger = logging.getLogger(__name__)

class AnthropicProvider(LLMProvider):
    """Anthropic API provider."""
    
    BASE_URL = "https://api.anthropic.com/v1"
    
    def _get_api_key(self) -> str:
        settings = get_settings()
        return settings.anthropic_api_key or ""

    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"error": True, "error_message": "Anthropic API key not configured"}

        model = model_id.removeprefix("anthropic:")

        # Convert messages to Anthropic format (system message is separate)
        system_message = ""
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                filtered_messages.append(msg)

        # Claude 4.x models have deprecated the temperature parameter
        MODELS_WITHOUT_TEMPERATURE = ("claude-opus-4", "claude-sonnet-4", "claude-haiku-4")
        supports_temperature = not any(model.startswith(p) for p in MODELS_WITHOUT_TEMPERATURE)

        payload = {
            "model": model,
            "messages": filtered_messages,
            "max_tokens": 4096,
        }
        if supports_temperature:
            payload["temperature"] = temperature
        if system_message:
            payload["system"] = system_message

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{self.BASE_URL}/messages",
                        headers=headers,
                        json=payload,
                    )

                if response.status_code == 429:
                    if attempt < max_retries:
                        # Respect Anthropic's retry-after header if present
                        retry_after_ms = response.headers.get("retry-after-ms")
                        retry_after = response.headers.get("retry-after")
                        if retry_after_ms:
                            delay = int(retry_after_ms) / 1000.0
                        elif retry_after:
                            delay = float(retry_after)
                        else:
                            delay = min(60.0, 15.0 * (2 ** attempt))  # 15s, 30s, 60s
                        logger.warning(
                            f"Anthropic rate limit on {model}: waiting {delay:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    return {
                        "error": True,
                        "error_message": f"Anthropic API error: {response.status_code} - {response.text}",
                    }

                if response.status_code != 200:
                    return {
                        "error": True,
                        "error_message": f"Anthropic API error: {response.status_code} - {response.text}",
                    }

                data = response.json()
                content = data["content"][0]["text"]
                return {"content": content, "error": False}

            except Exception as e:
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return {"error": True, "error_message": str(e)}

        return {"error": True, "error_message": "Anthropic: max retries exceeded"}

    async def get_models(self) -> List[Dict[str, Any]]:
        api_key = self._get_api_key()
        if not api_key:
            return []
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    }
                )
                
                if response.status_code != 200:
                    # Fallback to hardcoded list if API fails (e.g. older keys or API not enabled)
                    return [
                        {"id": "anthropic:claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "provider": "Anthropic"},
                        {"id": "anthropic:claude-3-opus-20240229", "name": "Claude 3 Opus", "provider": "Anthropic"},
                        {"id": "anthropic:claude-3-sonnet-20240229", "name": "Claude 3 Sonnet", "provider": "Anthropic"},
                        {"id": "anthropic:claude-3-haiku-20240307", "name": "Claude 3 Haiku", "provider": "Anthropic"},
                    ]
                    
                data = response.json()
                models = []
                
                for model in data.get("data", []):
                    if model.get("type") == "model":
                        models.append({
                            "id": f"anthropic:{model['id']}",
                            "name": f"{model.get('display_name', model['id'])} [Anthropic]",
                            "provider": "Anthropic"
                        })
                
                return sorted(models, key=lambda x: x["name"])
                
        except Exception:
            return []

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    }
                )

                if response.status_code == 200:
                    return {"success": True, "message": "API key is valid"}
                elif response.status_code == 401:
                    return {"success": False, "message": "Invalid API key"}
                else:
                    error_detail = response.json().get("error", {}).get("message", response.text)
                    return {"success": False, "message": f"Anthropic error: {error_detail}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
