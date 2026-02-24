"""AES-256-GCM encryption and HKDF key derivation for vault data."""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

NONCE_SIZE = 12  # 96-bit nonce for GCM
KEY_SIZE = 32  # 256-bit key


def generate_master_key() -> bytes:
    """Generate a new random 256-bit master key."""
    return os.urandom(KEY_SIZE)


def derive_hmac_key(master_key: bytes) -> bytes:
    """Derive a separate HMAC key from the master key using HKDF."""
    hkdf = HKDF(
        algorithm=SHA256(),
        length=KEY_SIZE,
        salt=None,
        info=b"cloakroom-hmac-v1",
    )
    return hkdf.derive(master_key)


def derive_vault_key(master_key: bytes) -> bytes:
    """Derive the vault encryption key from the master key using HKDF."""
    hkdf = HKDF(
        algorithm=SHA256(),
        length=KEY_SIZE,
        salt=None,
        info=b"cloakroom-vault-v1",
    )
    return hkdf.derive(master_key)


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt with AES-256-GCM. Returns nonce + ciphertext + tag."""
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt AES-256-GCM. Input is nonce + ciphertext + tag."""
    nonce = data[:NONCE_SIZE]
    ciphertext = data[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)
