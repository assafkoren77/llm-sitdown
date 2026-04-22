"""OpenAI provider implementation."""

import httpx
from typing import List, Dict, Any
from .base import LLMProvider
from ..settings import get_settings

class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""
    
    BASE_URL = "https://api.openai.com/v1"
    
    def _get_api_key(self) -> str:
        settings = get_settings()
        return settings.openai_api_key or ""

    async def query(self, model_id: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {"error": True, "error_message": "OpenAI API key not configured"}
            
        # Strip prefix if present
        model = model_id.removeprefix("openai:")
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 1.0 if any(x in model for x in ["gpt-5.1", "o1-", "o3-"]) else temperature
                    }
                )
                
                if response.status_code != 200:
                    error_body = response.text
                    try:
                        msg = response.json().get("error", {}).get("message", error_body)
                        if "not a chat model" in msg:
                            msg = f"'{model}' does not support the chat completions API. Remove it from your council and choose a GPT or o-series model instead."
                    except Exception:
                        msg = error_body
                    return {"error": True, "error_message": f"OpenAI API error: {response.status_code} - {msg}"}
                    
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "error": False}
                
        except Exception as e:
            return {"error": True, "error_message": str(e)}

    async def get_models(self) -> List[Dict[str, Any]]:
        api_key = self._get_api_key()
        if not api_key:
            return []
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                
                if response.status_code != 200:
                    return []
                    
                data = response.json()
                models = []
                NON_CHAT_PATTERNS = [
                    "audio", "realtime", "voice", "tts", "dall-e", "whisper",
                    "embed", "transcribe", "sora", "batch", "computer-use",
                    "search", "moderat", "instruct", "base",
                ]
                CHAT_PREFIXES = ("gpt-3.5", "gpt-4", "gpt-5", "o1", "o3", "o4")
                for model in data.get("data", []):
                    mid = model["id"].lower()
                    if any(x in mid for x in NON_CHAT_PATTERNS):
                        continue
                    if any(mid.startswith(p) for p in CHAT_PREFIXES):
                        models.append({
                            "id": f"openai:{model['id']}",
                            "name": f"{model['id']} [OpenAI]",
                            "provider": "OpenAI"
                        })
                return sorted(models, key=lambda x: x["name"])
                
        except Exception:
            return []

    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                
                if response.status_code == 200:
                    return {"success": True, "message": "API key is valid"}
                else:
                    return {"success": False, "message": "Invalid API key"}
        except Exception as e:
            return {"success": False, "message": str(e)}
