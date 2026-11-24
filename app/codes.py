"""Génération des codes d'accès (lisibles sur mobile, ~60 bits d'entropie)."""
import hashlib
import secrets

# Pas de caractères ambigus (0/o, 1/l/i).
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


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
