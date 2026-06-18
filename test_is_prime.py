"""Simple tests for is_prime."""

from is_prime import is_prime


def test_is_prime():
    primes = [2, 3, 5, 7, 13, 97]
    non_primes = [-7, -1, 0, 1, 4, 9, 100]

    for p in primes:
        assert is_prime(p) is True, f"{p} should be prime"

    for c in non_primes:
        assert is_prime(c) is False, f"{c} should not be prime"


if __name__ == "__main__":
    test_is_prime()
    print("All tests passed.")
