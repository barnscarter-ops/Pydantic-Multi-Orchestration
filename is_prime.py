"""Prime-checking utility."""


def is_prime(n):
    """Return True if n is a prime number, False otherwise.

    Uses trial division up to sqrt(n) for efficiency.

    Args:
        n: An integer to test for primality.

    Returns:
        bool: True if n is prime, otherwise False.

    Raises:
        TypeError: If n is not an integer.
    """
    if not isinstance(n, int) or isinstance(n, bool):
        raise TypeError("is_prime() requires an integer argument")

    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False

    for divisor in range(3, int(n ** 0.5) + 1, 2):
        if n % divisor == 0:
            return False
    return True


if __name__ == "__main__":
    for value in range(20):
        print(f"{value}: {is_prime(value)}")
