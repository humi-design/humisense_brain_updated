"""Envelope credential encryption.

Design
------
* A single 256-bit master key is supplied out-of-band through the
  ``HUMISENSE_CREDENTIAL_ENCRYPTION_KEY`` environment variable.  It is never
  stored in the database.
* Each credential is sealed with AES-256-GCM under a per-record random nonce.
* The *associated data* binds the ciphertext to ``tenant_id`` +
  ``connection_id`` + key version.  Moving a ciphertext to another tenant or
  connection therefore fails authentication - cross-tenant credential reuse is
  impossible even with database write access.
* Only ciphertext, nonce and metadata are persisted.  Raw secrets never touch
  the database, the logs or the API surface.
"""

from __future__ import annotations

import base64
import os
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.errors import ConfigurationError, HumisenseError

_NONCE_BYTES = 12
_KEY_BYTES = 32


class CredentialDecryptionError(HumisenseError):
    status_code = 400
    code = "credential_decryption_failed"


def _decode_master_key(raw: str) -> bytes:
    raw = raw.strip()
    for decoder in (base64.b64decode, bytes.fromhex):
        try:
            candidate = decoder(raw)
        except Exception:  # noqa: BLE001 - try the next encoding
            continue
        if len(candidate) == _KEY_BYTES:
            return candidate
    raise ConfigurationError(
        "HUMISENSE_CREDENTIAL_ENCRYPTION_KEY must decode to exactly 32 bytes "
        "(base64 or hex encoded)."
    )


@dataclass(frozen=True)
class SealedCredential:
    ciphertext: bytes
    nonce: bytes
    key_version: int
    algorithm: str = "AES-256-GCM"

    def to_storage(self) -> dict[str, object]:
        return {
            "encrypted_payload": base64.b64encode(self.ciphertext).decode("ascii"),
            "nonce": base64.b64encode(self.nonce).decode("ascii"),
            "key_version": self.key_version,
            "algorithm": self.algorithm,
        }

    @classmethod
    def from_storage(cls, stored: dict[str, object]) -> SealedCredential:
        return cls(
            ciphertext=base64.b64decode(str(stored["encrypted_payload"])),
            nonce=base64.b64decode(str(stored["nonce"])),
            key_version=int(stored.get("key_version", 1)),  # type: ignore[arg-type]
            algorithm=str(stored.get("algorithm", "AES-256-GCM")),
        )


class CredentialCipher:
    """Stateless encrypt/decrypt facade bound to the configured master key."""

    def __init__(self, master_key: bytes | None = None, *, key_version: int | None = None) -> None:
        if master_key is None:
            raw = settings.credential_encryption_key
            if not raw:
                if settings.is_production:
                    raise ConfigurationError(
                        "HUMISENSE_CREDENTIAL_ENCRYPTION_KEY is required in production."
                    )
                # Development-only deterministic key so local runs work without
                # extra setup.  Never used when a real key is configured.
                master_key = b"\x00" * _KEY_BYTES
            else:
                master_key = _decode_master_key(raw)
        if len(master_key) != _KEY_BYTES:
            raise ConfigurationError("Credential master key must be 32 bytes.")
        self._aesgcm = AESGCM(master_key)
        self._key_version = key_version if key_version is not None else settings.credential_key_version

    @staticmethod
    def associated_data(tenant_id: str, connection_id: str, key_version: int) -> bytes:
        return f"humisense|credential|t:{tenant_id}|c:{connection_id}|v:{key_version}".encode()

    def seal(self, plaintext: dict[str, object], *, tenant_id: str, connection_id: str) -> SealedCredential:
        nonce = secrets.token_bytes(_NONCE_BYTES)
        aad = self.associated_data(tenant_id, connection_id, self._key_version)
        payload = _serialize(plaintext)
        ciphertext = self._aesgcm.encrypt(nonce, payload, aad)
        return SealedCredential(
            ciphertext=ciphertext, nonce=nonce, key_version=self._key_version
        )

    def open(
        self, sealed: SealedCredential, *, tenant_id: str, connection_id: str
    ) -> dict[str, object]:
        aad = self.associated_data(tenant_id, connection_id, sealed.key_version)
        try:
            payload = self._aesgcm.decrypt(sealed.nonce, sealed.ciphertext, aad)
        except InvalidTag as exc:  # wrong tenant/connection, tampered, or wrong key
            raise CredentialDecryptionError(
                "Credential could not be decrypted for this connection."
            ) from exc
        return _deserialize(payload)


def _serialize(plaintext: dict[str, object]) -> bytes:
    import json

    return json.dumps(plaintext, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _deserialize(payload: bytes) -> dict[str, object]:
    import json

    return json.loads(payload.decode("utf-8"))


def generate_master_key() -> str:
    """Helper for operators: generate a fresh base64 master key."""
    return base64.b64encode(os.urandom(_KEY_BYTES)).decode("ascii")


_cipher: CredentialCipher | None = None


def get_cipher() -> CredentialCipher:
    global _cipher
    if _cipher is None:
        _cipher = CredentialCipher()
    return _cipher
