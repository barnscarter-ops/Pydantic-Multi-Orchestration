import json
import time

import httpx

from core.base_provider import BaseProvider
from schemas.gateway import GatewayRequest, GatewayResponse


class LlamaCppProvider(BaseProvider):
    """OpenAI-compatible provider for llama.cpp and similar local inference servers."""

    def __init__(self, base_url: str = "http://localhost:8080/v1", api_key: str = "local"):
        super().__init__(api_key=api_key, base_url=base_url.rstrip("/"))

    async def generate(self, request: GatewayRequest, model: str) -> GatewayResponse:
        start_time = time.time()
        payload = self._build_payload(request, model, stream=False)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})

                return GatewayResponse(
                    content=message.get("content", ""),
                    model_used=model,
                    provider=self.get_provider_name(),
                    latency_ms=(time.time() - start_time) * 1000,
                    tokens_used=data.get("usage", {}).get("completion_tokens"),
                    escalated=False,
                )
        except Exception as e:
            return GatewayResponse(
                content="",
                model_used=model,
                provider=self.get_provider_name(),
                latency_ms=(time.time() - start_time) * 1000,
                error=str(e),
                escalated=False,
            )

    async def stream(self, request: GatewayRequest, model: str):
        payload = self._build_payload(request, model, stream=True)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            yield {
                                "content": delta.get("content", ""),
                                "model_used": model,
                                "provider": self.get_provider_name(),
                                "escalated": False,
                            }
                        except Exception:
                            continue
        except Exception as e:
            yield {
                "content": "",
                "model_used": model,
                "provider": self.get_provider_name(),
                "escalated": False,
                "error": str(e),
            }

    def get_provider_name(self) -> str:
        return "llamacpp"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, request: GatewayRequest, model: str, stream: bool) -> dict:
        messages = []
        for item in request.context or []:
            role = item.get("role", "user")
            content = item.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": request.prompt})

        return {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
