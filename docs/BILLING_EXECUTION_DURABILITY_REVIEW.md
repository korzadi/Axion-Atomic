# Billing execution durability review

Status: design review only. This document does not enable billing and does not authorize deployment.

## Verified source state

The current `api/billing_execution.py` helper reserves credits, invokes the inference callback, validates Ollama usage counters, and then settles the reservation. It does not call `claim_execution`, `persist_encrypted_result`, or an authenticated result cipher.

The separate `api/billing_execution_store.py` provides execution claims and encrypted-result persistence. `api/billing_result_crypto.py` provides AES-256-GCM with caller-supplied key management. Their existence does not make the orchestration path durable.

A test-only change was briefly committed with assertions for the intended future orchestration while the production helper remained unchanged. That mismatch was detected by source inspection and the test file was restored to the tests matching the current implementation in commit `808f3e71a1ebf9b4a3c70e5a10708f49afc09f91`. No passing CI is claimed for the temporary mismatch or the restoration commit.

## Required implementation order

1. Authenticate the session, validate CSRF, and authorize project membership before looking up any idempotency key.
2. Validate the client `Idempotency-Key` and compute a canonical fingerprint over the final server-built messages, effective RAG context, public model mapping, generation settings, and policy version.
3. In one durable transaction, create or recover the user-scoped reservation and fingerprint. A reused key with a different fingerprint returns conflict.
4. Claim exactly one execution for the reservation before calling Ollama. A pre-existing `started`, `unknown`, or `review` execution is never rerun.
5. Call the pinned runtime once and validate requested model, returned model, `done=true`, and both non-negative usage counters.
6. Serialize the complete response, encrypt it with authenticated context binding user, reservation, and execution IDs, then persist ciphertext and integrity metadata.
7. Only after successful durable ciphertext persistence, settle credits idempotently using verified usage.
8. Return the response only after the durable state is consistent. Completed retries must verify ciphertext integrity and decrypt under the authenticated user context. Unknown or incomplete results go to reconciliation and are never inferred again.

## Failure handling requirements

- If the provider times out or the caller is cancelled after execution may have started, mark execution and reservation uncertain; never retry inference automatically.
- If runtime validation, counters, encryption, persistence, or settlement fails, do not return an unverified response or perform an estimated charge.
- If settlement outcome is ambiguous, preserve the completed encrypted result and reconcile the ledger; do not rerun inference.
- A completed execution without a recoverable encrypted result is an integrity incident, not a reason to rerun.
- Production key management, rotation, access policy, and recovery must be configured outside the application code. A test cipher is never acceptable for live billing.

## Release gates still open

- The current helper must be rewritten and tested to follow the order above.
- HTTP `Idempotency-Key` integration and completed-result replay are not implemented.
- Final-prompt fingerprinting must include server-built RAG content, not merely client messages.
- Runtime model digest, template, tokenizer identity, and generation limits need a verifiable deployment attestation.
- PostgreSQL fault-injection tests must cover concurrent duplicate requests and crashes at each durable transition.
- Production KMS and backup/restore recovery must be validated.

**Release rule:** paid billing remains disabled until every gate is implemented, reviewed, and proven in CI and a controlled end-to-end environment. No VPS deployment is authorized by this review.
