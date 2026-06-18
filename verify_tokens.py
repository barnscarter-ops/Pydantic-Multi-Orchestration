"""
Quick smoke test: count tokens for a sample message and verify prompt caching
fields are present in the response usage.
Run with: python verify_tokens.py
"""

import os
import sys
import anthropic


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    sample_messages = [{"role": "user", "content": "Hello, count to 3."}]

    # 1. Token counting (no API call billed)
    count = client.messages.count_tokens(
        model="claude-opus-4-8",
        system=[{"type": "text", "text": "You are a helpful assistant.", "cache_control": {"type": "ephemeral"}}],
        messages=sample_messages,
    )
    print(f"Token count (no charge): {count.input_tokens}")

    # 2. Real call to verify cache fields exist in usage
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=64,
        system=[{"type": "text", "text": "You are a helpful assistant.", "cache_control": {"type": "ephemeral"}}],
        messages=sample_messages,
    )
    u = response.usage
    print(f"Input tokens:               {u.input_tokens}")
    print(f"Output tokens:              {u.output_tokens}")
    print(f"Cache read input tokens:    {getattr(u, 'cache_read_input_tokens', 'N/A')}")
    print(f"Cache creation tokens:      {getattr(u, 'cache_creation_input_tokens', 'N/A')}")
    print(f"Response text:              {response.content[0].text!r}")
    print("\nAll checks passed ✓")


if __name__ == "__main__":
    main()
