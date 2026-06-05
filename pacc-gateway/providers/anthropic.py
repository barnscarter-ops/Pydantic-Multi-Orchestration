import httpx
import time
from core.base_provider import BaseProvider
from schemas.gateway import GatewayRequest, GatewayResponse

class AnthropicProvider(BaseProvider):
    """Implementation of the Anthropic Claude provider."""

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key)

    async def generate(self, request: GatewayRequest, model: str) -> GatewayResponse:
        start_time = time.time()

        # Using the Messages API
        payload = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": request.prompt}]
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()

                latency = (time.time() - start_time) * 1000

                return GatewayResponse(
                    content=data["content"][0]["text"],
                    model_used=model,
                    provider=self.get_provider_name(),
                    latency_ms=latency,
                    tokens_used=data.get("usage", {}).get("output_tokens"),
                    escalated=True # This is a paid fallback
                )

        except Exception as e:
            return GatewayResponse(
                content="",
                model_used=model,
                provider=self.get_provider_name(),
                latency_ms=(time.time() - start_time) * 1000,
                error=str(e),
                escalated=True
            )

    async def stream(self, request: GatewayRequest, model: str):
        payload = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": request.prompt}],
            "stream": True
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers=headers
                ) as response:
                    response.raise_for_status()
                    import json
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                if data.get("type") == "content_block_delta":
                                    text = data.get("delta", {}).get("text", "")
                                    yield {
                                        "content": text,
                                        "model_used": model,
                                        "provider": self.get_provider_name(),
                                        "escalated": True
                                    }
                            except Exception:
                                pass
        except Exception as e:
            yield {
                "content": "",
                "model_used": model,
                "provider": self.get_provider_name(),
                "escalated": True,
                "error": str(e)
            }

    def get_provider_name(self) -> str:
        return "anthropic"
