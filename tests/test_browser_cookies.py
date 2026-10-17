"""Tests for Chromium cookie decryption (v10 blobs)."""

import os
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from shelf.browser_cookies import CookieError, _decrypt_v10


def encrypt_v10(key, plaintext):
    """Build a Chromium-style v10 blob: 'v10' + AES-CBC(key, iv=spaces)."""
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).encryptor()
    return b"v10" + enc.update(padded) + enc.finalize()


KEY = os.urandom(16)


class TestDecryptV10:
    def test_legacy_plaintext(self):
        blob = encrypt_v10(KEY, b"cookie-value-123")
        assert _decrypt_v10(KEY, blob) == "cookie-value-123"

    def test_modern_host_hash_prefix_stripped(self):
        # Chromium >=130 prepends SHA-256(host_key) to the plaintext.
        blob = encrypt_v10(KEY, sha256(b"learning.oreilly.com").digest() + b"jwt-token")
        assert _decrypt_v10(KEY, blob) == "jwt-token"

    def test_wrong_key_raises(self):
        blob = encrypt_v10(KEY, b"secret")
        with pytest.raises((CookieError, ValueError)):
            _decrypt_v10(os.urandom(16), blob)
