"""Real signed-token helpers for the authentication tests.

Nothing here is mocked: a genuine RSA key pair is generated, tokens are signed
with the private half, and a real JWKS document is served over HTTP so
``PyJWKClient`` fetches it exactly as it would from an identity provider.  The
verification path under test is therefore the production path.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://idp.humisense.test/"
AUDIENCE = "humisense-api"
KID = "test-key-1"


def _b64u(value: int) -> str:
    import base64

    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class SigningKey:
    """An RSA key pair plus its public JWKS representation."""

    def __init__(self, kid: str = KID) -> None:
        self.kid = kid
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.private_key.public_key()
        self.pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def jwk(self) -> dict:
        numbers = self.public_key.public_numbers()
        return {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": self.kid,
            "n": _b64u(numbers.n),
            "e": _b64u(numbers.e),
        }

    def sign(self, claims: dict, *, kid: str | None = None, algorithm: str = "RS256") -> str:
        headers = {"kid": kid or self.kid}
        return jwt.encode(claims, self.private_key, algorithm=algorithm, headers=headers)


def claims(**overrides) -> dict:
    """A valid claim set, overridable per test."""
    import time

    now = int(time.time())
    base = {
        "sub": "user-1",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "nbf": now - 5,
        "exp": now + 600,
        "email": "user@example.test",
        "name": "Test User",
    }
    base.update(overrides)
    return base


class JwksServer:
    """Serves a real JWKS document over HTTP for PyJWKClient to fetch."""

    def __init__(self, keys: list[SigningKey]) -> None:
        self.keys = keys
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/jwks.json"

    def start(self) -> JwksServer:
        keys = self.keys

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/jwks.json":
                    body = json.dumps({"keys": [k.jwk() for k in keys]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):  # silence the test output
                return

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def wrong_key_token(signing_key: SigningKey, **overrides) -> str:
    """A token signed by an untrusted key but carrying a trusted ``kid``.

    Exercises the signature check specifically: the header points at a key the
    server trusts, but the signature does not verify against it.
    """
    rogue = SigningKey(kid=signing_key.kid)
    return rogue.sign(claims(**overrides))
