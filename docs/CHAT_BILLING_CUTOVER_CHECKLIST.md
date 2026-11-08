# Chat billing cutover — production gates

Status: **durable ledger integration implemented; paid billing remains disabled by configuration**. This is not evidence of a production deployment, a real charge, or a completed PostgreSQL/Ollama E2E.

## Current request path
`POST /workspace/chat/completions` requires a web session, CSRF, and project membership. When `BILLING_ENFORCEMENT_ENABLED=true` it also:

1. Requires `Idempotency-Key` (1–200 characters) before RAG or inference.
2. Verifies the configured Ollama artifact against the deployment manifest (model digest, template SHA-256, tokenizer architecture).
3. Builds the effective prompt including server-selected RAG context.
4. Derives a stable request UUID and a payload fingerprint that covers the effective messages, generation settings, policy version, public model, runtime model, digest, template, and tokenizer.
5. Reserves credits transactionally, claims exactly one execution, calls Ollama once, validates measured counters and returned model, encrypts the result, and settles idempotently.
6. Returns `usage_billing.mode="ledger"` only after a confirmed settlement.

With billing disabled, the route remains shadow/free and does not reserve or charge. The legacy `/v1/chat/completions` route uses a shared API key, not a user identity; never attach user billing to it.

## Implemented and unit-tested
- [x] Pure request identity helpers (`api/billing_request_identity.py`), including an attested fingerprint over the final server-built prompt/RAG context.
- [x] HTTP `Idempotency-Key` enforcement and stable user-scoped request UUIDs in `workspace_chat`.
- [x] Runtime attestation (`api/runtime_attestation.py`) for exact model digest, template SHA-256, and tokenizer architecture. It fails closed before retrieval, reservation, or inference.
- [x] Durable reserve → claim → inference → encrypt → settle orchestration (`api/billing_execution_durable.py`).
- [x] Encrypted completed-result recovery without re-running inference (`api/billing_recovery.py`).
- [x] CSRF-protected, permission-gated, audited admin recovery endpoint `POST /admin/billing/executions/recover` (`billing.manage`, `global_admin_audit_events`) with a confirmation-gated control in the admin portal.
- [x] CSRF-protected, permission-gated admin reconciliation endpoint `POST /admin/billing/reservations/reconcile-no-execution` for `unknown`/`review` reservations, backed by the append-only reconciliation table and global admin audit.
- [x] Unit tests for identity, attestation, durable states, recovery, authorization, and workspace chat wiring.

## Mandatory release gates

### 1. Identity and idempotency
- Reject missing, oversized, or malformed keys before any side effect.
- Same key with a different effective payload must return 409, never create another charge.
- Fingerprint must include the final server-built prompt/RAG context and attested runtime identity.
- [ ] Prove concurrent duplicate requests and payload mismatches against PostgreSQL.

### 2. Runtime and budget attestation
- [x] Map the public catalog model to the configured Ollama runtime.
- [x] Verify model digest, template, tokenizer architecture, context, and generation limits before paid execution.
- [ ] Populate and review real deployment manifest values (`BILLING_RUNTIME_MODEL_DIGEST`, `BILLING_RUNTIME_TEMPLATE_SHA256`, `BILLING_TOKENIZER_CONTRACT`).
- [ ] Verify the manifest matches the exact production Ollama artifact and restart procedure.

### 3. Durable execution
- [x] Reserve transactionally before inference and claim exactly one execution.
- [x] Never repeat inference after a started, completed, or uncertain claim.
- [x] Verify requested/returned model, `done=true`, and both non-negative Ollama token counters.
- [x] Encrypt and persist the response before settlement.
- [x] Preserve uncertain state for reconciliation; no silent refund, rerun, or estimate.
- [ ] Exercise interruption at each state transition and lost commit acknowledgements against PostgreSQL.

### 4. Settlement and response
- [x] Settle once, idempotently, using verified counters and a published policy version.
- [x] Over-reservation or ledger invariant failures go to review.
- [x] Bind result decryption to authenticated user, reservation, and execution IDs.
- [x] Never log prompts, responses, ciphertext, secrets, or cross-user identifiers.
- [ ] Validate reconciliation and recovery procedures on a disposable PostgreSQL database.

### 5. Production key management
- [ ] Replace `EnvironmentResultKeyProvider` with production KMS or a managed key provider.
- [ ] Define rotation, version retention, recovery, access policy, and incident response.
- [ ] Verify database backups alone cannot decrypt stored inference results.
- [x] Encryption key is validated before credits are reserved.

### 6. Proof before release
- [ ] Run PostgreSQL concurrency/interruption/recovery tests.
- [ ] Run E2E against the exact pinned Ollama model/tokenizer/template.
- [ ] Verify backup/restore, ledger reconciliation, alerting, and support procedures.
- [ ] Publish prices/quotas and enable paid billing only in a separately reviewed configuration change.

## Prohibited before release
- Charging shadow events or estimated tokens.
- Treating a shared API key as a user identity.
- Trusting client project IDs without membership authorization.
- Re-running uncertain inference.
- Crediting screenshots or unverified webhooks.
- Advertising paid plans or enabling checkout while the catalog is preview-only.

## Remaining blockers
- Production KMS and recovery/rotation procedures are not established.
- Runtime manifest values are not configured or verified against a production deployment.
- PostgreSQL concurrency, interruption, and restore proofs are still missing.
- QvaPay Lightning Address order correlation and server-to-server verification remain unconfirmed.
- Real OAuth credentials/callbacks and production session configuration require validation.
- Paid billing, checkout, and public prices remain disabled.

**Release rule:** this checklist is a cutover specification, not evidence that every gate has passed. Production billing remains disabled until the owner authorizes a separately reviewed change.
