"""Tests for vault encryption."""

import pytest

from cowork_shield.vault.crypto import (
    decrypt,
    derive_hmac_key,
    derive_vault_key,
    encrypt,
    generate_master_key,
)


class TestGenerateMasterKey:
    def test_key_length(self):
        key = generate_master_key()
        assert len(key) == 32

    def test_keys_are_unique(self):
        k1 = generate_master_key()
        k2 = generate_master_key()
        assert k1 != k2


class TestKeyDerivation:
    def test_hmac_key_is_deterministic(self):
        master = generate_master_key()
        h1 = derive_hmac_key(master)
        h2 = derive_hmac_key(master)
        assert h1 == h2

    def test_vault_key_is_deterministic(self):
        master = generate_master_key()
        v1 = derive_vault_key(master)
        v2 = derive_vault_key(master)
        assert v1 == v2

    def test_hmac_and_vault_keys_differ(self):
        master = generate_master_key()
        h = derive_hmac_key(master)
        v = derive_vault_key(master)
        assert h != v

    def test_different_masters_produce_different_keys(self):
        m1 = generate_master_key()
        m2 = generate_master_key()
        assert derive_hmac_key(m1) != derive_hmac_key(m2)


class TestEncryptDecrypt:
    def test_round_trip(self):
        key = generate_master_key()
        plaintext = b"Hello, World! This is sensitive data."
        encrypted = encrypt(plaintext, key)
        decrypted = decrypt(encrypted, key)
        assert decrypted == plaintext

    def test_wrong_key_fails(self):
        key1 = generate_master_key()
        key2 = generate_master_key()
        encrypted = encrypt(b"secret", key1)
        with pytest.raises(Exception):
            decrypt(encrypted, key2)

    def test_tampered_data_fails(self):
        key = generate_master_key()
        encrypted = encrypt(b"secret", key)
        tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 0xFF])
        with pytest.raises(Exception):
            decrypt(tampered, key)

    def test_empty_plaintext(self):
        key = generate_master_key()
        encrypted = encrypt(b"", key)
        decrypted = decrypt(encrypted, key)
        assert decrypted == b""

    def test_unicode_plaintext(self):
        key = generate_master_key()
        plaintext = "Unicode: cafe\u0301 \u2603 \U0001f600".encode("utf-8")
        encrypted = encrypt(plaintext, key)
        decrypted = decrypt(encrypted, key)
        assert decrypted == plaintext
