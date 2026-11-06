# Chat billing cutover — production gates

Status: **shadow metering only; paid billing is not enabled**. This specification does not enable charges or authorize VPS deployment.

## Current request path
`POST /workspace/chat/completions` requires web session and CSRF, checks project membership, calls Ollama with usage metadata, records best-effort shadow usage, and rejects a requested/returned model mismatch. It does not reserve or settle credits.

The legacy `/v1/chat/completions` route uses a shared API key, not a user identity. Never attach user billing to that route until per-user API-key identity and project authorization exist.

## Mandatory release gates

### 1. Identity and idempotency
- Require a strict client idempotency key.
- Derive a stable request UUID scoped to authenticated user and key.
- [x] Pure helper hashes canonical request data: model, project, messages, generation settings, and policy version (`api/billing_request_identity.py`).
- [ ] The HTTP endpoint still does not require or persist `Idempotency-Key`; helper availability alone is not HTTP idempotency.
- Same key with different payload must conflict, never create another charge.
- The fingerprint must cover the final server-built prompt/RAG context, not only client messages.
- Follow `docs/HTTP_CHAT_IDEMPOTENCY_DESIGN.md` for the required request order and failure semantics.

### 2. Runtime and budget attestation
- Map public catalog model to the exact configured Ollama runtime.
- Pin and verify model digest, template, tokenizer identity, context, and generation limits.
- Reserve using a verified tokenizer/runtime contract only. If any input is unavailable, reject paid execution or remain explicitly shadow/free. Never bill guessed token counts.

### 3. Durable execution
- Reserve transactionally before inference and claim exactly one execution.
- Never repeat inference after a started, completed, or uncertain claim.
- Verify requested and returned model, `done=true`, and both non-negative Ollama token counters.
- Encrypt and persist the response before settlement.
- On uncertainty, preserve state for reconciliation; do not silently refund, rerun, or charge estimates.

### 4. Settlement and response
- Settle once, idempotently, using verified counters and a published pricing policy.
- Over-reservation or ledger invariant failures go to review.
- Bind result decryption to authenticated user, reservation, and execution IDs.
- Never log prompts, responses, ciphertext, secrets, or cross-user identifiers.

### 5. Production key management
- Replace injectable/test cipher provider with production KMS or managed key provider.
- Define rotation, version retention, recovery, access policy, and incident response.
- Verify database backups alone cannot decrypt stored inference results.

### 6. Proof before release
- Test concurrent duplicate requests, payload mismatch, interruption at each state transition, lost commit acknowledgements, usage mismatch, over-reservation, settlement retries, and cross-user access against PostgreSQL.
- Run end-to-end against the exact pinned Ollama model/tokenizer/template.
- Verify backup/restore, ledger reconciliation, alerting, and support procedures.
- Only after every gate passes, publish prices/quotas and enable paid billing in a separately reviewed configuration change.

## Prohibited before release
- Charging shadow events or estimated tokens.
- Treating a shared API key as a user identity.
- Trusting client project IDs without membership authorization.
- Re-running uncertain inference.
- Crediting screenshots or unverified webhooks.
- Advertising paid plans or enabling checkout while the catalog is preview-only.

## Known blockers
- Workspace chat is shadow-only, not connected to durable reservations/settlement.
- HTTP idempotency is not wired into the route; durable execution recovery and encrypted response replay are not integrated.
- Runtime digest, tokenizer, and template are not attested by a deployment manifest.
- Production KMS and recovery/rotation procedures are not established.
- QvaPay Lightning Address order correlation and server-to-server verification remain unconfirmed.
- Real OAuth credentials/callbacks and production session configuration require validation.

**Implementation note:** The current workspace chat path remains shadow-only. Do not describe it as idempotent until the endpoint atomically persists the user/key/fingerprint and connects it to durable execution recovery.

**Release rule:** this checklist is a cutover specification, not evidence that any gate has passed. Production billing remains disabled.
