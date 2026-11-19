"""Encrypt/decrypt Access URL at rest (Persistence-Design §4)."""

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("firesimplefin.storage")

# Fernet expects a url-safe base64-encoded 32-byte key.
# We accept: (1) raw base64 32-byte key (e.g. openssl rand -base64 32), or
# (2) pre-made Fernet key (url-safe base64).


def _fernet_from_env_key(key_str: str) -> Fernet:
    key_str = key_str.strip()
    # If it looks like standard base64 (e.g. from openssl rand -base64 32), decode to 32 bytes then url-safe encode.
    try:
        raw = base64.standard_b64decode(key_str)
    except Exception:
        raw = None
    if raw and len(raw) == 32:
        fernet_key = base64.urlsafe_b64encode(raw)
        return Fernet(fernet_key)
    # Otherwise treat as Fernet key (url-safe base64, 44 chars).
    return Fernet(key_str.encode("ascii"))


def encrypt_access_url(access_url: str, encryption_key: str) -> bytes:
    """Encrypt Access URL for storage. Key from ENCRYPTION_KEY (never log or return)."""
    f = _fernet_from_env_key(encryption_key)
    return f.encrypt(access_url.encode("utf-8"))


def decrypt_access_url(ciphertext: bytes, encryption_key: str) -> str:
    """Decrypt stored Access URL. Raises ValueError if key wrong or tampered."""
    f = _fernet_from_env_key(encryption_key)
    try:
        return f.decrypt(ciphertext).decode("utf-8")
    except InvalidToken as e:
        logger.warning("Decryption failed (wrong key or tampered data)")
        raise ValueError("Decryption failed") from e
