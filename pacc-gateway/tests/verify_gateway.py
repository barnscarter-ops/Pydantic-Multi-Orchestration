import asyncio
import os
from dotenv import load_dotenv
from core.config_loader import ConfigLoader
from core.router import ModelRouter
from schemas.gateway import GatewayRequest

# Load env for the test
load_dotenv("pacc-gateway/.env")

async def test_local_success():
    print("\n--- Testing Local Success (Ollama) ---")
    config = ConfigLoader("pacc-gateway/config.yaml")
    router = ModelRouter(config, os.environ)

    request = GatewayRequest(
        prompt="Hello, who are you?",
        agent_role="general"
    )

    response = await router.route(request)
    print(f"Model Used: {response.model_used}")
    print(f"Provider: {response.provider}")
    print(f"Content: {response.content[:100]}...")
    assert response.provider == "ollama"
    assert response.content != ""

async def test_escalation_trigger():
    print("\n--- Testing Escalation Trigger (Simulated Failure) ---")
    config = ConfigLoader("pacc-gateway/config.yaml")
    router = ModelRouter(config, os.environ)

    # To simulate a local failure without breaking the real Ollama,
    # we can temporarily point the router to a non-existent Ollama URL
    router.providers["ollama"].base_url = "http://localhost:9999"

    request = GatewayRequest(
        prompt="This should trigger escalation because local is down.",
        agent_role="general"
    )

    response = await router.route(request)
    print(f"Model Used: {response.model_used}")
    print(f"Provider: {response.provider}")
    print(f"Escalated: {response.escalated}")

    # If API key is missing in .env, this will still fail but it should
    # at least have attempted the 'anthropic' provider.
    assert response.escalated == True
    assert response.provider == "anthropic"

async def main():
    try:
        await test_local_success()
        await test_escalation_trigger()
        print("\n✅ Gateway Verification Complete!")
    except Exception as e:
        print(f"\n❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
