import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.router import ModelRouter
from providers.llamacpp import LlamaCppProvider
from schemas.gateway import GatewayRequest


def main():
    load_dotenv(PROJECT_ROOT / ".env")

    router = ModelRouter(
        registry_url=os.environ.get("REGISTRY_URL", "http://localhost:8001"),
        env_vars=os.environ,
    )

    qwen_route = "llamacpp/Qwen3-Coder-30B-A3B-Instruct-UD-Q3_K_XL.gguf"
    provider_key = router._get_provider_for_model(qwen_route)
    assert provider_key == "llamacpp", f"Expected llamacpp provider, got {provider_key}"
    assert isinstance(router.providers[provider_key], LlamaCppProvider)

    request = GatewayRequest(
        prompt="Smoke test",
        agent_id="mav-coder",
        stream=True,
        metadata={
            "editor_file_path": str(PROJECT_ROOT / "config.yaml"),
            "editor_file_content": "default_local_model: smoke-test",
        },
    )
    assert request.agent_id == "mav-coder"
    assert request.metadata["editor_file_path"].endswith("config.yaml")

    print("Gateway smoke verification passed.")
    print(f"Route: {qwen_route}")
    print(f"Provider: {provider_key}")
    print(f"llama.cpp base URL: {router.providers[provider_key].base_url}")


if __name__ == "__main__":
    main()
