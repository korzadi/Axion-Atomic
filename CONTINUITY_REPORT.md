# Continuity report — AXYRON ATOMIC

Date: 2026-11-08
Branch: `main`
Base HEAD: `ac91a09` (no commit or push performed in this block)

## Implemented in this block

- Added `api/runtime_attestation.py`: verifies the exact Ollama model digest, template SHA-256, and tokenizer architecture against `/api/tags` and `/api/show`, with a 300-second cache. Failures fail closed before retrieval, reservation, or inference.
- Hardened `POST /workspace/chat/completions` when `BILLING_ENFORCEMENT_ENABLED=true`:
  - Requires `Idempotency-Key` and validates its full printable-ASCII alphabet before attestation, RAG, reservation, or inference.
  - Attests runtime before any user-visible work.
  - Fingerprints the effective server-built prompt (including RAG) plus public model, runtime model, digest, template, tokenizer, generation settings, and policy version.
  - Validates the result-encryption key before reserving credits.
- Added `POST /admin/billing/reservations/reconcile-no-execution` for `unknown`/`review` reservations, with CSRF, `billing.manage`, human confirmation, append-only reconciliation, and global audit.
- Added `POST /admin/billing/executions/recover`:
  - Requires `billing.manage` and CSRF.
  - Writes an append-only audit event before attempting recovery.
  - Retries settlement of encrypted completed results without repeating inference.
  - Never returns prompts, ciphertext, or secrets.
- Updated the admin portal (`frontend/admin.js`) to show real mutation availability and provide a confirmation-gated recovery control with an auditable reason.
- Updated readiness: `chat_execution="integrated"` plus a real `runtime_attestation` gate; ledger readiness requires key + manifest.
- Fixed idempotent settlement to return the original consumed credits instead of `None`, so a retried completed request reports the same logical charge.
- Corrected stale billing documentation in `BILLING_RESERVATIONS_LEDGER_SCHEMA.md`, `COMMERCIAL_BILLING_TECHNICAL_DESIGN.md`, `FRONTEND_STUDIO_STATUS.md`, `PRODUCTION_INITIAL_RELEASE_GATE.md`, and `PROJECT_COMPLETION_GAP_ANALYSIS.md`.
- Added `.env.example` manifest variables.
- Reconciled stale billing/idempotency docs and the acceptance matrix with the actual implementation.

## Files changed

- New: `api/runtime_attestation.py`, `api/sandbox_runtime.py`, `tests/test_runtime_attestation.py`, `tests/test_workspace_agent_reconciliation_http.py`, `tests/test_workspace_agent_cancellation_http.py`, `tests/test_sandbox_runner.py`, `tests/test_sandbox_runtime_config.py`, `migrations/022_agent_run_cancellation.sql`
- Modified: `api/workspace_routes.py`, `api/admin_routes.py`, `api/config.py`, `api/readiness.py`, `api/billing_reservations.py`, `api/schemas.py`, `agent/run_store.py`, `agent/coding_agent.py`
- Modified: `frontend/admin.js`, `frontend/studio.js`
- Tests updated: `tests/test_workspace_chat_billing.py`, `tests/test_admin_audit_routes.py`, `tests/test_readiness.py`, `tests/test_frontend_studio_spa.py`, `tests/test_billing_reservations_postgres.py`, `tests/test_workspace_agent_runtime_http.py`, `tests/test_agent_run_store.py`, `tests/test_coding_agent_persistence.py`, `tests/test_project_agent_runtime.py`, `tests/test_postgres_migrations.py`
- Docs/config: `.env.example`, `AGENTS.md`, `docs/CHAT_BILLING_CUTOVER_CHECKLIST.md`, `docs/HTTP_CHAT_IDEMPOTENCY_DESIGN.md`, `docs/V1_ACCEPTANCE_MATRIX.md`, `docs/BILLING_RESERVATIONS_LEDGER_SCHEMA.md`, `docs/COMMERCIAL_BILLING_TECHNICAL_DESIGN.md`, `docs/FRONTEND_STUDIO_STATUS.md`, `docs/PRODUCTION_INITIAL_RELEASE_GATE.md`, `docs/PROJECT_COMPLETION_GAP_ANALYSIS.md`, `docs/AGENT_RUNTIME_API_STATUS.md`

## Verification run

- `python -m compileall -q api agent core rag sandbox audit tests scripts` — passed.
- `python -m pytest -q` con un enlace temporal `python` -> `python3` — **812 passed, 9 skipped** (las 9 son PostgreSQL).
- `python -m pytest -q --ignore=tests/test_sandbox_exec.py --ignore=tests/test_agent_sandbox.py` sin el enlace — **791 passed, 9 skipped**.
- `python3 scripts/check_frontend_js.py` — all inline scripts plus `workspace.js`, `studio.js`, and `admin.js` syntactically valid.
- `git diff --check` — clean.
- The 9 skipped tests are PostgreSQL-gated unless `DATABASE_URL` starts with `postgresql`.
- The sandbox tests pass locally when a temporary `python` -> `python3` symlink is available; without it they are excluded because `LocalBackend` invokes `python`. CI has `python`.

## Not run / blocked

- No real PostgreSQL concurrency, interruption, restore, or migration test.
- No E2E against the pinned Ollama artifact or runtime manifest.
- No Docker image build, deployment, restart, or production change.
- No paid billing, checkout, prices, or payment-provider activation.
- CI status for this working tree is unconfirmed; nothing was committed or pushed.
- Untracked real `.env.*` backup files were left untouched and must never be committed.

## Next recommended steps

1. Run the PostgreSQL concurrency/interruption/recovery tests against a disposable database with an explicit environment variable.
2. Configure and verify a real runtime manifest (`BILLING_RUNTIME_MODEL_DIGEST`, `BILLING_RUNTIME_TEMPLATE_SHA256`, `BILLING_TOKENIZER_CONTRACT`) against the exact deployment artifact.
3. Run the CI workflow on a commit and confirm pytest, JS, shell, Docker smoke, Playwright, Qdrant, and PostgreSQL jobs.
4. Design production KMS/rotation before any paid billing discussion.
5. Keep `BILLING_ENFORCEMENT_ENABLED=false` and checkout disabled until the owner explicitly authorizes cutover.

## Sandbox Docker block — 2026-11-08

- Replaced the local bind mount in `DockerBackend` with tar-over-stdin into a private tmpfs `/workspace`, enabling a remote dedicated daemon without the host Docker socket.
- Added `api/sandbox_runtime.py` and `SANDBOX_DOCKER_*` settings; disabled by default, digest-pinned images, `ssh://` or TLS-verified `tcp://`, and fail-closed 503 on misconfiguration.
- Added tests for tar snapshot filtering, no bind mount, stdin forwarding, cleanup, TLS requirements, `--pull=never`, and route 503 behavior.
- Still blocked: no dedicated daemon, TLS certificates, digest-pinned sandbox images, Docker CLI in the API image, or real E2E. Not enabled and no infrastructure changed.

## Agent runtime block — 2026-11-08

- Verified the persistent agent runtime is connected to `POST /workspace/agent/runs`, `POST /workspace/agent/runs/{run_id}/resume`, run listing/detail, and action/plan approval endpoints.
- Confirmed per-operation SQLAlchemy pooling via `SqlAlchemyMetaStore`, project-scoped workspace composition, action-hash approvals, and fail-closed handling of interrupted `running` actions.
- Added `RunNotFoundError` so missing or cross-project runs are distinguishable from storage failures.
- Mapped agent HTTP errors: missing/foreign run → 404, unusable approval → 409, invalid input → 422, workspace unavailable → 503. No internal details are returned.
- Added regression tests for the new error mapping and the `RunNotFoundError` path.
- Verification: `python -m pytest -q` (con enlace temporal `python` -> `python3`) → **812 passed, 9 skipped**; sin el enlace, suite sin sandbox → **791 passed, 9 skipped**. `compileall`, frontend JS syntax and `git diff --check` passed.
- Added `POST /workspace/agent/runs/{run_id}/reconcile` for owner/admin: an interrupted `running` action can be marked `applied` or `failed` with a mandatory reason, atomically audited, and left for explicit resume. The runtime never re-executes it.
- Updated Axyron Studio with confirmation-gated reconciliation controls and regression coverage.
- Added `POST /workspace/agent/runs/{run_id}/cancel` for owner/admin and migration 022: only `awaiting_approval` runs can be cancelled; pending approvals/actions are invalidated atomically, audited as `agent.run.cancel`, and cancelled runs never restart the model. Viewer/editor controls were gated in Studio.
- Added cancelled-run guards so a late resume/snapshot cannot overwrite `cancelled` and new actions cannot be recorded after cancellation; concurrent resumption maps to HTTP 409.
- Cancellation now locks approvals before actions, matching approval-decision order to avoid deadlocks, and rechecks `running` after locking. Sandbox audit commands are redacted before storage.
- Still blocked: Docker sandbox integration (AGT-04), real Ollama/sandbox E2E, and CI confirmation for the current working tree. No commit, push, deploy, migration, or infrastructure change was performed.
