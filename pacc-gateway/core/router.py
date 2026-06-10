import json
import logging
import httpx
import time
from pathlib import Path
from typing import Dict, Any, Optional
from core.base_provider import BaseProvider
from providers.ollama import OllamaProvider
from providers.anthropic import AnthropicProvider
from providers.llamacpp import LlamaCppProvider
from schemas.gateway import GatewayRequest, GatewayResponse, AgentManifest

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pacc-router")

class ModelRouter:
    """The core escalation engine that implements the Handshake Protocol with the Registry."""

    def __init__(self, registry_url: str, env_vars: Dict[str, str]):
        self.registry_url = registry_url.rstrip('/')

        local_agents_path = env_vars.get("LOCAL_AGENTS_FILE", str(Path(__file__).resolve().parents[1] / "local_agents.json"))
        self._local_agents: Dict[str, AgentManifest] = {}
        if local_agents_path:
            try:
                data = json.loads(Path(local_agents_path).read_text(encoding="utf-8"))
                self._local_agents = {k: AgentManifest(**v) for k, v in data.items()}
                logger.info(f"Loaded {len(self._local_agents)} local agent(s) from {local_agents_path}")
            except Exception as e:
                logger.warning(f"Could not load local agents file at {local_agents_path}: {e}")

        # Initialize providers
        self.providers: Dict[str, BaseProvider] = {
            "ollama": OllamaProvider(base_url=env_vars.get("OLLAMA_BASE_URL", "http://localhost:11434")),
            "llamacpp": LlamaCppProvider(
                base_url=env_vars.get("LLAMACPP_BASE_URL", "http://localhost:8080/v1"),
                api_key=env_vars.get("LLAMACPP_API_KEY", "local")
            ),
            "anthropic": AnthropicProvider(api_key=env_vars.get("ANTHROPIC_API_KEY")),
            # OpenAI and Google would be added here
        }

    async def _fetch_manifest(self, agent_id: str) -> Optional[AgentManifest]:
        """Fetch agent policy from Registry, falling back to local_agents.json if unavailable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.registry_url}/agents/{agent_id}")
                if response.status_code == 200:
                    return AgentManifest(**response.json())
                logger.warning(f"Registry returned {response.status_code} for agent {agent_id}, trying local fallback")
        except Exception as e:
            logger.warning(f"Registry unreachable ({e}), trying local fallback for agent {agent_id}")

        manifest = self._local_agents.get(agent_id)
        if manifest:
            logger.info(f"Using local manifest for agent {agent_id} (model: {manifest.primary_model})")
            return manifest

        logger.error(f"No manifest found for agent {agent_id} in registry or local file")
        return None

    async def route(self, request: GatewayRequest) -> GatewayResponse:
        """
        Routes the request based on the manifest fetched from the Registry.
        Request -> Registry (Handshake) -> Local Model -> Paid Model
        """
        # Inject active editor file context if provided in metadata
        if request.metadata:
            editor_path = request.metadata.get("editor_file_path")
            editor_content = request.metadata.get("editor_file_content")
            if editor_path and editor_content:
                context_str = (
                    f"[CONTEXT: ACTIVE EDITOR FILE]\n"
                    f"File: {editor_path}\n"
                    f"Content:\n"
                    f"```\n{editor_content}\n```\n"
                    f"[END OF CONTEXT]\n\n"
                )
                request.prompt = context_str + request.prompt

        # 1. Handshake: Fetch Policy
        logger.info(f"Performing handshake for agent: {request.agent_id}")
        manifest = await self._fetch_manifest(request.agent_id)

        if not manifest:
            return GatewayResponse(
                content="",
                model_used="unknown",
                provider="none",
                latency_ms=0,
                error=f"Policy failure: Could not retrieve manifest for agent {request.agent_id}",
                escalated=False
            )

        primary_model = manifest.primary_model
        fallback_model = manifest.fallback_model

        # We can now use the params from the manifest for the request
        request.temperature = manifest.params.temperature
        request.max_tokens = manifest.params.max_tokens

        # Check for forced escalation
        if getattr(request, "force_escalate", False):
            logger.warning(f"Forced escalation requested. Routing directly to fallback {fallback_model}...")
            provider_key = self._get_provider_for_model(fallback_model)
            if provider_key in self.providers:
                response = await self.providers[provider_key].generate(request, fallback_model)
            else:
                logger.error(f"Provider for {fallback_model} not configured.")
                response = GatewayResponse(
                    content="",
                    model_used=fallback_model,
                    provider="none",
                    latency_ms=0,
                    error=f"Fallback provider {provider_key} not available",
                    escalated=True
                )
            return response

        # 2. Attempt Primary (Local)
        logger.info(f"Attempting primary model: {primary_model} (Policy: {manifest.name})")
        primary_provider = self._get_provider_for_model(primary_model)
        response = await self.providers[primary_provider].generate(request, primary_model)

        # 3. Check if we need to escalate
        if self._should_escalate(response):
            logger.warning(f"Local model {primary_model} failed or insufficient. Escalating to {fallback_model}...")

            # 4. Attempt Fallback (Paid)
            provider_key = self._get_provider_for_model(fallback_model)
            if provider_key in self.providers:
                response = await self.providers[provider_key].generate(request, fallback_model)
            else:
                logger.error(f"Provider for {fallback_model} not configured.")
                response.error = f"Fallback provider {provider_key} not available"

        return response

    async def route_stream(self, request: GatewayRequest):
        """
        Routes the streaming request based on the manifest fetched from the Registry.
        """
        # Inject active editor file context if provided in metadata
        if request.metadata:
            editor_path = request.metadata.get("editor_file_path")
            editor_content = request.metadata.get("editor_file_content")
            if editor_path and editor_content:
                context_str = (
                    f"[CONTEXT: ACTIVE EDITOR FILE]\n"
                    f"File: {editor_path}\n"
                    f"Content:\n"
                    f"```\n{editor_content}\n```\n"
                    f"[END OF CONTEXT]\n\n"
                )
                request.prompt = context_str + request.prompt

        logger.info(f"Performing handshake for agent stream: {request.agent_id}")
        manifest = await self._fetch_manifest(request.agent_id)

        if not manifest:
            yield {
                "content": "",
                "model_used": "unknown",
                "provider": "none",
                "escalated": False,
                "error": f"Policy failure: Could not retrieve manifest for agent {request.agent_id}"
            }
            return

        primary_model = manifest.primary_model
        fallback_model = manifest.fallback_model

        # Apply params
        request.temperature = manifest.params.temperature
        request.max_tokens = manifest.params.max_tokens

        # Check for forced escalation
        if getattr(request, "force_escalate", False):
            logger.warning(f"Forced escalation requested for stream. Routing directly to fallback {fallback_model}...")
            provider_key = self._get_provider_for_model(fallback_model)
            if provider_key in self.providers:
                try:
                    async for chunk in self.providers[provider_key].stream(request, fallback_model):
                        yield chunk
                except Exception as e:
                    yield {
                        "content": "",
                        "model_used": fallback_model,
                        "provider": provider_key,
                        "escalated": True,
                        "error": str(e)
                    }
            else:
                yield {
                    "content": "",
                    "model_used": fallback_model,
                    "provider": "none",
                    "escalated": True,
                    "error": f"Fallback provider {provider_key} not available"
                }
            return

        # Attempt Primary (Local)
        logger.info(f"Attempting primary stream model: {primary_model}")
        primary_provider = self._get_provider_for_model(primary_model)
        
        local_failed = False
        local_error = None
        try:
            yielded_any = False
            async for chunk in self.providers[primary_provider].stream(request, primary_model):
                if chunk.get("error"):
                    if not yielded_any:
                        local_failed = True
                        local_error = chunk.get("error")
                        break
                yielded_any = True
                yield chunk
        except Exception as e:
            logger.warning(f"Primary model stream threw exception: {e}")
            local_failed = True
            local_error = str(e)

        if local_failed:
            logger.warning(f"Local stream failed: {local_error}. Escalating to fallback {fallback_model}...")
            fallback_provider = self._get_provider_for_model(fallback_model)
            if fallback_provider in self.providers:
                try:
                    async for chunk in self.providers[fallback_provider].stream(request, fallback_model):
                        yield chunk
                except Exception as e:
                    yield {
                        "content": "",
                        "model_used": fallback_model,
                        "provider": fallback_provider,
                        "escalated": True,
                        "error": str(e)
                    }
            else:
                yield {
                    "content": "",
                    "model_used": fallback_model,
                    "provider": "none",
                    "escalated": True,
                    "error": f"Fallback provider {fallback_provider} not available"
                }

    def _should_escalate(self, response: GatewayResponse) -> bool:
        """Determines if the response warrants escalation."""
        if response.error:
            return True
        if not response.content or len(response.content.strip()) == 0:
            return True
        return False

    def _get_provider_for_model(self, model_name: str) -> str:
        """Maps a model name to its provider key."""
        if "claude" in model_name.lower():
            return "anthropic"
        if "gpt" in model_name.lower():
            return "openai"
        if "gemini" in model_name.lower():
            return "google"
        if model_name.lower().startswith("llamacpp/") or model_name.lower().endswith(".gguf"):
            return "llamacpp"
        return "ollama"
