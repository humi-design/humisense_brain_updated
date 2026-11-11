"""Credential encryption tests.

Proves: ciphertext is not plaintext, tampering fails, and - critically -
ciphertext is bound to (tenant, connection) so it cannot be replayed across
tenants or connections.
"""

from __future__ import annotations

import pytest

from app.core.crypto import CredentialCipher, CredentialDecryptionError, generate_master_key

KEY_A = b"\x01" * 32
KEY_B = b"\x02" * 32


def test_seal_produces_ciphertext_not_plaintext():
    cipher = CredentialCipher(KEY_A)
    sealed = cipher.seal({"password": "hunter2"}, tenant_id="t1", connection_id="c1")
    stored = sealed.to_storage()
    assert "hunter2" not in str(stored)
    assert stored["algorithm"] == "AES-256-GCM"
    assert stored["nonce"]


def test_open_roundtrip():
    cipher = CredentialCipher(KEY_A)
    payload = {"password": "hunter2", "api_key": "abc"}
    sealed = cipher.seal(payload, tenant_id="t1", connection_id="c1")
    assert cipher.open(sealed, tenant_id="t1", connection_id="c1") == payload


def test_ciphertext_is_bound_to_tenant():
    """A credential sealed for tenant A must not decrypt for tenant B."""
    cipher = CredentialCipher(KEY_A)
    sealed = cipher.seal({"token": "secret"}, tenant_id="tenant-a", connection_id="c1")
    with pytest.raises(CredentialDecryptionError):
        cipher.open(sealed, tenant_id="tenant-b", connection_id="c1")


def test_ciphertext_is_bound_to_connection():
    cipher = CredentialCipher(KEY_A)
    sealed = cipher.seal({"token": "secret"}, tenant_id="t1", connection_id="c1")
    with pytest.raises(CredentialDecryptionError):
        cipher.open(sealed, tenant_id="t1", connection_id="c2")


def test_wrong_master_key_fails():
    sealed = CredentialCipher(KEY_A).seal({"token": "s"}, tenant_id="t1", connection_id="c1")
    with pytest.raises(CredentialDecryptionError):
        CredentialCipher(KEY_B).open(sealed, tenant_id="t1", connection_id="c1")


def test_tampered_ciphertext_fails():
    cipher = CredentialCipher(KEY_A)
    sealed = cipher.seal({"token": "secret"}, tenant_id="t1", connection_id="c1")
    tampered = sealed.to_storage()
    raw = bytearray(sealed.ciphertext)
    raw[0] ^= 0xFF
    tampered["encrypted_payload"] = __import__("base64").b64encode(bytes(raw)).decode()

    from app.core.crypto import SealedCredential

    with pytest.raises(CredentialDecryptionError):
        cipher.open(SealedCredential.from_storage(tampered), tenant_id="t1", connection_id="c1")


def test_nonce_is_unique_per_seal():
    cipher = CredentialCipher(KEY_A)
    a = cipher.seal({"x": 1}, tenant_id="t1", connection_id="c1")
    b = cipher.seal({"x": 1}, tenant_id="t1", connection_id="c1")
    assert a.nonce != b.nonce
    assert a.ciphertext != b.ciphertext


def test_generate_master_key_is_32_bytes():
    import base64

    assert len(base64.b64decode(generate_master_key())) == 32
