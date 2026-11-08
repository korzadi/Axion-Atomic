# HTTP chat idempotency and durable execution design

Status: **implemented in the workspace HTTP route and unit-tested; production billing remains disabled**. PostgreSQL concurrency/interruption E2E and production KMS are still pending. This document does not enable billing, change runtime configuration, or authorize deployment.

## Current verified boundary

When `BILLING_ENFORCEMENT_ENABLED=true`, `POST /workspace/chat/completions` authenticates the web session, validates CSRF, checks project membership, requires `Idempotency-Key`, verifies the runtime manifest, builds the effective prompt with server-selected RAG, reserves credits, claims one execution, performs one Ollama inference, validates usage/model, encrypts the result, and settles idempotently. When billing is disabled the route remains shadow/free.

Existing building blocks:
- `stable_request_id(user_id, idempotency_key)` validates printable ASCII keys (1–200 chars) and scopes a stable UUID to the user.
- `attested_request_payload_sha256(...)` hashes canonical JSON containing the effective server-built messages, public model, attested runtime model/digest/template/tokenizer, generation settings, and policy version.
- `reserve_credits(...)` serializes user/key reservation attempts and rejects payload/policy mismatches.
- `claim_execution(...)` creates one execution row per reservation and never reclaims started/unknown work.
- `persist_encrypted_result(...)` stores ciphertext only; `load_encrypted_result(...)` verifies its SHA-256.
- `AesGcmResultCipher` requires an injected key provider; no production KMS provider is configured.
- `recover_completed_billing_executions(...)` and the audited admin endpoint `POST /admin/billing/executions/recover` retry settlement for completed encrypted results without another inference.
- `reconcile_confirmed_no_execution(...)` and the audited admin endpoint `POST /admin/billing/reservations/reconcile-no-execution` release `unknown`/`review` reservations only after explicit human confirmation of no execution.

These building blocks are wired into the workspace route. PostgreSQL concurrency and process-interruption proofs are still required.

## Required request order

1. Validate request schema and strict `Idempotency-Key` syntax.
2. Authenticate session and validate CSRF.
3. Authorize membership and role for the requested project.
4. Resolve the public model ID to the server-controlled exact runtime model.
5. Build the final server-side message list, including system prompt and retrieved context. The fingerprint must represent the effective request, not merely the client-supplied messages.
6. Compute the canonical payload fingerprint and stable user-scoped request UUID.
7. Calculate a preflight upper bound only from a verified runtime/tokenizer/template contract. If attestation fails, the route returns 503 before retrieval, reservation, inference, or charge.
8. In one durable transaction, create or retrieve the user/key reservation and its fingerprint. Same key + different fingerprint returns HTTP 409. The unique constraint and advisory lock remain the final concurrency authority.
9. For a new reservation, claim exactly one execution before calling Ollama. A concurrent duplicate must not call Ollama.
10. Call Ollama once. Require exact requested/returned runtime match, `done=true`, and valid non-negative prompt/output counters.
11. Encrypt the complete response using a production-managed key, with authenticated context bound to user, reservation, and execution IDs.
12. Persist ciphertext and metadata durably. Only after this succeeds may verified usage be settled transactionally.
13. Return the response. A retry for a completed request loads, integrity-checks, decrypts, and returns the saved result without another inference or settlement.

## Duplicate and failure behavior

| Situation | Required behavior |
|---|---|
| Same user/key and same fingerprint, completed | Return saved encrypted result after integrity/authentication checks |
| Same user/key, different fingerprint | HTTP 409; do not infer or reserve again |
| Concurrent first requests | Exactly one execution claim wins; losers wait/re-read or receive a retryable conflict, never infer |
| Existing started/unknown execution | Never rerun; return a stable pending/unknown response and require reconciliation |
| Ollama timeout/cancellation or lost response | Mark execution and reservation uncertain; retain reserved credits; never assume no execution |
| Invalid/missing usage counters or model mismatch | Do not settle; move to unknown/review |
| Encryption/KMS unavailable | Fail closed; do not persist plaintext and do not settle |
| Ciphertext persistence fails | Do not settle; mark uncertain if inference may have completed |
| Settlement result is review or exceeds reservation | Do not return a success that implies billing completed; preserve review state |
| User/project authorization fails | Reject before looking up or revealing an idempotency record |

## Important implementation constraints

- The reservation's `UNIQUE(user_id, idempotency_key)` is the canonical idempotency uniqueness boundary. Do not add a second independent key registry unless a migration and consistency protocol are justified.
- `request_id` is UUID and unique; derive it deterministically from authenticated user + validated key.
- The request fingerprint must include the effective server-built prompt/RAG context or a stable digest of it, the exact runtime model, generation settings, and the immutable billing policy version. A client-only message hash is insufficient when the server adds context.
- Do not persist prompts or plaintext responses in the idempotency table. Persist only necessary identity/fingerprint/state metadata and encrypted result bytes.
- Keep the legacy shared-key `/v1/chat/completions` route outside user billing until it has per-user credentials and project authorization.
- Do not settle before the encrypted result is durably persisted. The durable orchestration enforces this order; verify it under fault injection.
- Do not use a development/test key provider as a production KMS substitute.

## Required tests before enabling the route

1. Key syntax, length, whitespace/control/non-ASCII rejection.
2. Same user/key/payload returns the same request identity; different users do not collide.
3. Same key + changed project, effective messages/RAG context, runtime, generation settings, or policy returns 409.
4. PostgreSQL concurrency test with multiple HTTP requests proves exactly one Ollama invocation.
5. Completed retry returns byte-equivalent logical response without another Ollama invocation or ledger mutation.
6. Started/unknown retry never calls Ollama again, including process crash and lost commit acknowledgement simulations.
7. Fault injection after reservation, claim, inference, encryption, result persistence, and settlement.
8. Cross-user and cross-project lookup attempts reveal no record or response.
9. KMS rotation, key revocation, restore, and decrypt-after-restore tests.
10. End-to-end test against pinned model digest, template, tokenizer, context, and Ollama usage metadata.

## Release decision

Unit tests pass for the implemented order, but PostgreSQL concurrency/interruption tests, the real runtime manifest, and production KMS are still missing. Keep paid billing and checkout disabled and do not publish prices until those gates pass. This design document is not proof of production readiness.
