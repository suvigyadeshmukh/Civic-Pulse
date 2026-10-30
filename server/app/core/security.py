"""Civic Pulse — Security utilities: password hashing, JWT, and PII encryption.

Three independent sub-systems live here so that every domain module imports a
single ``app.core.security`` namespace:

1. **Argon2id password hashing** — via ``argon2-cffi``
2. **JWT creation & validation** — via ``python-jose``
3. **AES-256-GCM PII vault cipher** — via ``cryptography.hazmat``
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

# ========================================================================== #
# 1.  Argon2id Password Hashing
# ========================================================================== #

_ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain: str) -> str:
    """Hash *plain* using Argon2id and return the PHC-format hash string."""
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches the Argon2id *hashed* value.

    Transparently handles rehashing checks (``needs_rehash``) — callers
    should update the stored hash if this function signals it, but that is
    left to the identity domain service.
    """
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError, HashingError):
        return False


def password_needs_rehash(hashed: str) -> bool:
    """Return ``True`` when the stored hash parameters are outdated."""
    return _ph.check_needs_rehash(hashed)


# ========================================================================== #
# 2.  JSON Web Token (JWT) helpers
# ========================================================================== #


def create_access_token(
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Mint a signed JWT embedding *subject* (user-id) and *role*.

    Parameters
    ----------
    subject:
        Typically the user's UUID string.
    role:
        One of ``CITIZEN``, ``BUSINESS_OWNER``, ``OFFICER``, ``ADMIN``.
    expires_delta:
        Override the configured ``ACCESS_TOKEN_EXPIRE_MINUTES``.
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, object] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(
        payload,
        _settings.JWT_SECRET_KEY,
        algorithm=_settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT, returning its claims dict.

    Raises
    ------
    jose.JWTError
        If the token is expired, tampered with, or structurally invalid.
    """
    try:
        payload: dict = jwt.decode(
            token,
            _settings.JWT_SECRET_KEY,
            algorithms=[_settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        logger.warning("JWT decode failed for token (first 20 chars): %s…", token[:20])
        raise


# ========================================================================== #
# 3.  AES-256-GCM PII Vault Cipher
# ========================================================================== #

_PII_KEY_BYTES: bytes = base64.b64decode(_settings.PII_ENCRYPTION_KEY)
_aesgcm = AESGCM(_PII_KEY_BYTES)

# GCM standard nonce length
_NONCE_LEN = 12


def encrypt_pii_dict(payload: dict) -> bytes:
    """Serialise *payload* to JSON and encrypt with AES-256-GCM.

    Returns ``nonce (12 B) || ciphertext+tag`` as a single ``bytes`` object
    suitable for storing in a PostgreSQL ``BYTEA`` column.
    """
    plaintext = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    nonce = os.urandom(_NONCE_LEN)
    ciphertext_with_tag: bytes = _aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext_with_tag


def decrypt_pii_dict(blob: bytes) -> dict:
    """Reverse :func:`encrypt_pii_dict`: split nonce, decrypt, parse JSON.

    Parameters
    ----------
    blob:
        The raw ``BYTEA`` value previously produced by :func:`encrypt_pii_dict`.

    Raises
    ------
    cryptography.exceptions.InvalidTag
        If the blob has been tampered with or the wrong key is used.
    """
    nonce = blob[:_NONCE_LEN]
    ciphertext_with_tag = blob[_NONCE_LEN:]
    plaintext = _aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    return json.loads(plaintext.decode("utf-8"))

