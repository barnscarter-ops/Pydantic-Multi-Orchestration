import httpx
import time
from core.base_provider import BaseProvider
from schemas.gateway import GatewayRequest, GatewayResponse

class OllamaProvider(BaseProvider):
    """Implementation of the Ollama local model provider."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        super().__init__(base_url=base_url)
        self.base_url = base_url

    async def generate(self, request: GatewayRequest, model: str) -> GatewayResponse:
        start_time = time.time()

        payload = {
            "model": model,
            "prompt": request.prompt,
            "stream": request.stream,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

                latency = (time.time() - start_time) * 1000

                return GatewayResponse(
                    content=data.get("response", ""),
                    model_used=model,
                    provider=self.get_provider_name(),
                    latency_ms=latency,
                    tokens_used=data.get("eval_count"),
                    confidence_score=None, # Ollama doesn't provide a native confidence score by default
                    escalated=False
                )

        except Exception as e:
            return GatewayResponse(
                content="",
                model_used=model,
                provider=self.get_provider_name(),
                latency_ms=(time.time() - start_time) * 1000,
                error=str(e),
                escalated=False
            )

    async def stream(self, request: GatewayRequest, model: str):
        payload = {
            "model": model,
            "prompt": request.prompt,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            import json
                            try:
                                data = json.loads(line)
                                yield {
                                    "content": data.get("response", ""),
                                    "model_used": model,
                                    "provider": self.get_provider_name(),
                                    "escalated": False
                                }
                            except Exception:
                                pass
        except Exception as e:
            yield {
                "content": "",
                "model_used": model,
                "provider": self.get_provider_name(),
                "escalated": False,
                "error": str(e)
            }

    def get_provider_name(self) -> str:
        return "ollama"
