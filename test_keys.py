import os
from dotenv import load_dotenv
load_dotenv()

try:
    import anthropic
    r = anthropic.Anthropic().messages.create(model="claude-sonnet-4-6", max_tokens=10, messages=[{"role":"user","content":"Say OK"}])
    print(f"[OK]   Sonnet: {r.content[0].text!r}")
except Exception as e:
    print(f"[FAIL] Sonnet: {e}")

try:
    from openai import OpenAI
    r = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY")).chat.completions.create(model=os.getenv("NVIDIA_MODEL"), messages=[{"role":"user","content":"Say OK"}], max_tokens=10)
    print(f"[OK]   Nemotron: {r.choices[0].message.content!r}")
except Exception as e:
    print(f"[FAIL] Nemotron: {e}")

try:
    from google import genai
    gc = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    r = gc.models.generate_content(model=os.getenv("GEMINI_MODEL"), contents="Say OK")
    print(f"[OK]   Gemini: {r.text!r}")
except Exception as e:
    print(f"[FAIL] Gemini: {e}")

try:
    from openai import OpenAI
    r = OpenAI(base_url=os.getenv("LLAMA_BASE_URL"), api_key="local").chat.completions.create(model=os.getenv("QWEN_MODEL"), messages=[{"role":"user","content":"Say OK"}], max_tokens=10, timeout=10)
    print(f"[OK]   Qwen: {r.choices[0].message.content!r}")
except Exception as e:
    print(f"[FAIL] Qwen: {e}")
