"""Security utilities and helpers for ACE."""

import secrets
import string


def generate_secure_id(prefix: str = "CERT", length: int = 12) -> str:
    """Generate a high-entropy cryptographically secure identifier."""
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}-{suffix}"


def verify_secret_token(token: str, expected_token: str) -> bool:
    """Constant-time token comparison to prevent timing attacks."""
    return secrets.compare_digest(token, expected_token)
