# Security Model — Humisense Brain, Layer 1

This document describes the security controls in the connector and sensory platform, what
each control actually enforces, and what the deployment is responsible for.

---

## 1. Trust boundaries

```
untrusted: browser, provider APIs, webhook senders, uploaded inventories
    │
    ├── edge / reverse proxy ── authenticates, injects X-Tenant-Id / X-User-Id / X-User-Role
    │
    ├── Layer 1 API ── validates identity, scopes every query by tenant
    │
    ├── credential vault ── AES-256-GCM, tenant-bound
    │
    └── egress guard ── allow-list, private-range denial, DNS re-check
            │
            └── provider APIs (untrusted responses, always re-validated)
```

**The edge is part of the security boundary.** Layer 1 trusts `X-Tenant-Id` and
`X-User-Role` because identity federation is not its responsibility. The deployment must
strip those headers from inbound client requests and set them from the authenticated session.
A deployment that forwards client-supplied identity headers defeats tenant isolation.

---

## 2. Tenant isolation

- Every table that holds tenant data carries a `tenant_id` column.
- Every repository query filters by the caller's tenant. There is no code path that reads a
  connection, credential, sync run, assessment or audit record without a tenant filter.
- A request for another tenant's resource returns **404**, not 403, so the API never confirms
  that the resource exists.
- Isolation violations are written to the audit log with the offending tenant and actor.
- `tests/test_tenant_isolation.py` covers cross-tenant read, write, revoke and credential
  decryption — 6 tests, all passing.

Production must additionally enable PostgreSQL row-level security on tenant tables as
defence in depth.

---

## 3. Credential protection

**At rest.** Credentials are encrypted with AES-256-GCM. The authenticated-encryption
additional data binds each ciphertext to its `tenant_id` and `connection_id`, so a ciphertext
copied into another tenant's row cannot be decrypted even with the master key.

**In transit to storage.** Credentials are accepted only over HTTPS in production, encrypted
before the database transaction commits, and the plaintext is not retained.

**In responses.** The API returns `credential_reference_id`, never credential material. No
endpoint echoes a stored secret.

**In logs.** A redaction filter strips values of keys matching `token`, `secret`, `password`,
`authorization`, `api_key` and `client_secret`. Structured logs record the *event* of a
credential use, never its value.

**Rotation.** `POST /connections/{id}/credentials` replaces the ciphertext and destroys the
previous value. Revocation destroys the credential outright; a revoked connection cannot
authenticate.

**Key management.** `HUMISENSE_CREDENTIAL_ENCRYPTION_KEY` must come from a secret manager.
The key is not stored beside the data. A database backup without the escrowed key cannot
decrypt stored credentials — key escrow is a deployment requirement.

**Development fallback — read this before running locally.** When no key is configured and
the environment is not production, the cipher uses a fixed all-zero 32-byte key. Credentials
created in development are therefore effectively unencrypted. Production refuses to start
without a real key, so this cannot leak into a production deployment, but it does mean local
databases must not be reused or promoted.

---

## 4. SSRF and egress control

Outbound requests from universal adapters are checked before dispatch:

| Check | Behaviour |
|---|---|
| Scheme | Only `http`/`https` are permitted. `file://`, `gopher://`, `dict://` and similar are rejected. In production the scheme set is narrower than in development. |
| Private ranges | `10/8`, `172.16/12`, `192.168/16`, `127/8`, link-local `169.254/16` and cloud metadata endpoints are denied by default. |
| Explicit block list | `HUMISENSE_EGRESS_BLOCKED_HOSTS` always blocks, and wins over the allow list. |
| Private-range exemption | `HUMISENSE_EGRESS_ALLOWED_HOSTS` or a per-connection `allow_private` flag exempts a host from the private-range check. The per-connection flag is **not currently written to the audit log** — see the residual-risk note. |
| Redirects | Automatic redirect following is disabled. When a redirect is handled explicitly, the new URL passes through `guard_url` again before the request. |
| DNS resolution | The hostname is resolved and every returned address is checked against the deny rules. |

### Residual SSRF risk: DNS rebinding (not fully closed)

`guard_url` resolves the hostname and validates the returned addresses, but the subsequent
HTTP request is issued to the **hostname**, so `httpx` performs its own resolution. The
validated addresses are carried on the `GuardedTarget` in `resolved_ips` and exposed via
`is_pinned()`, but **no code uses them to pin the connection to a validated IP**.

Consequence: a hostname that resolves to a public address during validation and a private
address microseconds later (a classic rebinding attack) is not prevented by the current code.
The window is narrow but real.

Mitigations available today:

- Run the service with network-layer egress rules that block private ranges, so a rebound
  connection cannot reach an internal target regardless of DNS.
- Keep `HUMISENSE_EGRESS_ALLOW_PRIVATE=false` and avoid per-connection `allow_private` unless
  the target genuinely is on-premise.

The correct code fix is to connect to a validated IP with the `Host` header and TLS SNI set to
the original name. This is recorded as a known risk in `FINAL_REPORT.md` rather than described
as solved.

`tests/test_egress.py` covers 11 cases including private-range denial, metadata-endpoint
denial, scheme rejection and allow/block precedence. It does not, and cannot, test a live
rebinding race.

---

## 5. Webhook verification

- The raw request body is used for signature computation; the parsed body is never used.
- The provider's scheme (`github`, `sha256`, `slack`) is applied per connection.
- Comparison is constant-time.
- A timestamp tolerance window rejects stale deliveries.
- Delivery ids are recorded; a replayed delivery is acknowledged as a duplicate and not
  reprocessed.
- Missing or invalid signatures return 401.
- The webhook secret is stored in the credential vault, not in configuration.

`tests/test_webhooks.py` covers 9 cases including forgery, replay and cross-tenant delivery.

---

## 6. Industrial safety

This is a deliberate, hard constraint.

- Industrial connectors (Canary, OPC UA, MQTT, historians, MES/CMMS/QMS) are **read-only by
  contract**. The Canary connector rejects any configuration requesting write capability.
- The sync engine refuses to run in write mode against a connector declared read-only.
- Layer 1 has no code path that writes to a PLC, setpoint, tag, machine control or physical
  equipment, and none may be added without an explicit safety review.
- Even where a provider API offers writes, Layer 1 defaults to read and requires explicit,
  audited enablement per connection.

---

## 7. Application security

| Control | Implementation |
|---|---|
| Authentication | Required on every endpoint except `/health`. |
| Authorisation | Writes require `admin`; reads require a valid identity. Enforced per route. |
| Input validation | Strict Pydantic models; unknown fields rejected; list and string lengths bounded. |
| SQL injection | The SQL adapter accepts query templates only, runs them on a read-only connection, rejects DDL/DML, and applies a statement timeout. Identifiers are never string-interpolated from user input. |
| Path traversal | The file adapter reads only inside `HUMISENSE_FILE_ADAPTER_ALLOWED_ROOTS`, resolving symlinks and rejecting `..`. |
| CORS | Explicit origin list, no wildcard with credentials. |
| Rate limiting | Per-connection limits plus provider 429 handling with backoff. |
| Error messages | Domain errors expose a code and a safe message; stack traces are never returned. |
| CSRF | Not applicable to the token/header API; the frontend sends no ambient cookies. |
| TLS | Verification is on by default for all egress and must not be disabled. |

---

## 8. Audit trail

Recorded with actor, tenant, action, resource and detail. The actions actually written by the
current code are:

`connection_created`, `connection_tested`, `connection_revoked`, `connection_deleted`,
`credential_rotated`, `resource_selected`, `sync_started`, `sync_succeeded`, `sync_failed`,
`tenant_isolation_violation`, and `webhook_rejected`.

A cross-tenant access attempt is recorded as `tenant_isolation_violation` with
`detail.reason = "cross_tenant_access_attempt"` while the caller still receives 404, so the
trail captures the attempt without confirming the resource exists.

Audit records are append-only from the application's perspective; there is no update or delete
endpoint.

### Declared but unused audit actions

`connection_updated`, `connection_authenticated` and `egress_blocked` exist in the
`AuditAction` enum but are never written. In particular, a blocked egress attempt is raised as
an error but **not** recorded in the audit log. Treat the audit trail as complete for
connection, credential and sync lifecycle events, and incomplete for egress denials.

---

## 9. What the deployment must do

1. Strip `X-Tenant-Id`, `X-User-Id` and `X-User-Role` from inbound client requests and inject
   them from the authenticated session.
2. Set `HUMISENSE_CREDENTIAL_ENCRYPTION_KEY` from a secret manager and escrow it.
3. Restrict `HUMISENSE_EGRESS_ALLOWLIST` to providers actually in use.
4. Keep `HUMISENSE_EGRESS_DENY_PRIVATE=true`.
5. Enable PostgreSQL row-level security on tenant tables.
6. Terminate TLS at the proxy and reject plaintext.
7. Configure log redaction in the aggregation pipeline as a second layer behind the
   in-process filter.
8. Back up the credentials table, and store the key separately from the backup.

---

## 10. Reporting

Security issues should be reported privately to the Humisense security contact rather than
through public issues. Include the affected endpoint, the tenant context and reproduction
steps. Do not include live credentials in a report.
