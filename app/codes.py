"""Génération des codes d'accès.

- collègues : 6 caractères, majuscules et chiffres, faciles à taper et à dicter ;
- admin : plus long (~80 bits), il protège le backoffice.
"""
import hashlib
import secrets

# Pas de caractères ambigus (0/O, 1/I/L).
ACCESS_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ACCESS_LENGTH = 6
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def generate_access_code() -> str:
    return "".join(secrets.choice(ACCESS_ALPHABET) for _ in range(ACCESS_LENGTH))


def generate_admin_code() -> str:
    return generate_code(4)


def generate_code(groups: int = 3, size: int = 4) -> str:
    return "-".join(
        "".join(secrets.choice(ALPHABET) for _ in range(size)) for _ in range(groups)
    )


def normalize(code: str) -> str:
    """Tolère espaces, majuscules et tirets oubliés."""
    raw = "".join(c for c in (code or "").lower() if c.isalnum())
    return raw


def fingerprint(code: str) -> str:
    return hashlib.sha256(("iodej:" + normalize(code)).encode()).hexdigest()


def matches(given: str, expected: str) -> bool:
    return secrets.compare_digest(normalize(given), normalize(expected))
