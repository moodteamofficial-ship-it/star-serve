"""Password hashing with Argon2id."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Trivial / previously seeded values that must never be stored or accepted.
FORBIDDEN_PASSWORDS = frozenset(
    {
        "111111",
        "123456",
        "password",
        "Password",
        "qwerty",
        "abcdef",
    }
)

MIN_PASSWORD_LENGTH = 6


def assert_password_strength(password: str) -> str:
    """Raise ValueError when a password is too weak to store."""
    value = password or ""
    if value in FORBIDDEN_PASSWORDS or value.lower() in {p.lower() for p in FORBIDDEN_PASSWORDS}:
        raise ValueError("This password is not allowed")
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return value


def is_forbidden_password(password: str) -> bool:
    value = password or ""
    return value in FORBIDDEN_PASSWORDS or value.lower() in {p.lower() for p in FORBIDDEN_PASSWORDS}


def hash_password(password: str, *, enforce_strength: bool = True) -> str:
    if enforce_strength:
        assert_password_strength(password)
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
