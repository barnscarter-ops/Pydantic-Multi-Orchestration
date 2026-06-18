"""
utils.py — General-purpose utility functions.
"""

def reverse_string(s: str) -> str:
    """
    Reverse the characters of a string.

    Uses slice notation (s[::-1]) which reverses Unicode code points.
    Note: This does NOT handle grapheme clusters (e.g., multi-codepoint emoji
    or combined characters) — for those cases, a grapheme-aware library is needed.

    Design decision: Only str inputs are accepted. Passing a non-str will raise
    TypeError rather than attempting duck-type coercion.

    Args:
        s (str): The input string to reverse.

    Returns:
        str: A new string with characters in reverse order.

    Raises:
        TypeError: If the input is not a str.

    Examples:
        >>> reverse_string("hello")
        'olleh'
        >>> reverse_string("")
        ''
        >>> reverse_string("a")
        'a'
        >>> reverse_string("racecar")
        'racecar'
    """
    if not isinstance(s, str):
        raise TypeError(f"Expected str, got {type(s).__name__!r}")
    return s[::-1]


if __name__ == "__main__":
    # Smoke tests — will raise AssertionError loudly on regression
    assert reverse_string("hello") == "olleh"
    assert reverse_string("") == ""
    assert reverse_string("a") == "a"
    assert reverse_string("racecar") == "racecar"
    assert reverse_string("Hello, World!") == "!dlroW ,olleH"

    # TypeError guard
    try:
        reverse_string(123)
        assert False, "Expected TypeError was not raised"
    except TypeError:
        pass

    print("All smoke tests passed.")