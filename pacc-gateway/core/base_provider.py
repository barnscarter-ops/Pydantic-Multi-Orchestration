from abc import ABC, abstractmethod
from schemas.gateway import GatewayRequest, GatewayResponse

class BaseProvider(ABC):
    """Abstract Base Class for all PACC Model Providers."""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def generate(self, request: GatewayRequest, model: str) -> GatewayResponse:
        """
        Generates a response from the LLM.

        Args:
            request: The unified GatewayRequest.
            model: The specific model name to use (e.g., 'llama3', 'claude-3-5-sonnet').

        Returns:
            A unified GatewayResponse.
        """
        pass

    @abstractmethod
    async def stream(self, request: GatewayRequest, model: str):
        """
        Yields dict chunks from the LLM.

        Args:
            request: The unified GatewayRequest.
            model: The specific model name to use.

        Yields:
            Dict chunks.
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the name of the provider (e.g., 'ollama', 'anthropic')."""
        pass
