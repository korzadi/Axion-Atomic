import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.billing_budget import InferenceBudget
from api.billing_execution import (
    DuplicateExecution,
    ModelExecutionMismatch,
    ResultPersistenceRequired,
    UsageReviewRequired,
    execute_reserved_inference,
)
from api.billing_policy import UsageUnavailable
from api.billing_reservations import ReservationResult, SettlementResult
from api.billing_execution_store import ExecutionClaim
from api.billing_result_crypto import EncryptedResult


MODEL = "atomic-code:16k-8k"
BUDGET = InferenceBudget(
    policy_version="atomic-code-budget-v1",
    runtime_model=MODEL,
    tokenizer_contract="qwen2_byte_fallback",
    input_tokens_upper_bound=100,
    output_tokens_upper_bound=50,
    input_weight=1,
    output_weight=1,
    reserved_credits=150,
    context_window=16384,
)
RESERVATION = ReservationResult("00000000-0000-0000-0000-000000000001", "held", 150)
CLAIM = ExecutionClaim("00000000-0000-0000-0000-000000000003", "started", True)
SETTLED = SettlementResult(RESERVATION.reservation_id, "settled", 20)


class FakeCipher:
    def encrypt(self, plaintext, **context):
        assert plaintext
        assert context["reservation_id"] == RESERVATION.reservation_id
        return EncryptedResult(b"ciphertext", b"n" * 12, "test-key")


def _result(**overrides):
    values = dict(
        content="private answer", requested_model=MODEL, returned_model=MODEL, done=True,
        prompt_eval_count=12, eval_count=8, usage_source="ollama_response",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _run(result=None, *, inference=None, settlement=None, cipher=None):
    return asyncio.run(execute_reserved_inference(
        engine=object(), user_id="user-1", project_id="project-1",
        request_id="00000000-0000-0000-0000-000000000002",
        idempotency_key="request-key-1", payload_sha256="a" * 64,
        budget=BUDGET, expected_runtime_model=MODEL,
        inference_call=inference or AsyncMock(return_value=result or _result()),
        reservation_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        result_cipher=cipher or FakeCipher(),
    ))


def _successful_patches(order=None):
    order = order if order is not None else []
    return (
        patch("api.billing_execution.reserve_credits", side_effect=lambda **kw: (
            order.append("reserve"), RESERVATION
        )[1]),
        patch("api.billing_execution.claim_execution", side_effect=lambda **kw: (
            order.append("claim"), CLAIM
        )[1]),
        patch("api.billing_execution.persist_encrypted_result", side_effect=lambda **kw: order.append("persist")),
        patch("api.billing_execution.settle_reservation", side_effect=lambda **kw: (
            order.append("settle"), SETTLED
        )[1]),
        order,
    )


def test_encrypted_result_is_durable_before_settlement():
    order = []
    async def infer():
        order.append("infer")
        return _result()

    reserve, claim, persist, settle, _ = _successful_patches(order)
    with reserve, claim, persist, settle:
        result = _run(inference=infer)

    assert order == ["reserve", "claim", "infer", "persist", "settle"]
    assert result.settlement.state == "settled"


def test_idempotent_reservation_never_repeats_inference():
    inference = AsyncMock(return_value=_result())
    repeated = ReservationResult(RESERVATION.reservation_id, "held", 150, True)
    with patch("api.billing_execution.reserve_credits", return_value=repeated):
        with pytest.raises(DuplicateExecution):
            _run(inference=inference)
    inference.assert_not_awaited()


def test_existing_execution_claim_never_repeats_inference():
    inference = AsyncMock(return_value=_result())
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.claim_execution", return_value=ExecutionClaim(CLAIM.execution_id, "started", False)),
    ):
        with pytest.raises(DuplicateExecution):
            _run(inference=inference)
    inference.assert_not_awaited()


@pytest.mark.parametrize("bad", [
    _result(returned_model="other-model"),
    _result(done=False),
])
def test_model_mismatch_or_incomplete_execution_keeps_reservation_unknown(bad):
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.claim_execution", return_value=CLAIM),
        patch("api.billing_execution.mark_execution_unknown") as execution_unknown,
        patch("api.billing_execution.mark_reservation_unknown") as reservation_unknown,
    ):
        with pytest.raises(ModelExecutionMismatch):
            _run(result=bad)
    execution_unknown.assert_called_once()
    reservation_unknown.assert_called_once()


def test_missing_provider_counters_keep_reservation_unknown():
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.claim_execution", return_value=CLAIM),
        patch("api.billing_execution.mark_execution_unknown"),
        patch("api.billing_execution.mark_reservation_unknown") as unknown,
    ):
        with pytest.raises(UsageUnavailable):
            _run(result=_result(prompt_eval_count=None, usage_source="unavailable"))
    unknown.assert_called_once()


def test_inference_exception_keeps_execution_and_reservation_unknown():
    async def fail():
        raise TimeoutError("provider timeout")
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.claim_execution", return_value=CLAIM),
        patch("api.billing_execution.mark_execution_unknown") as execution_unknown,
        patch("api.billing_execution.mark_reservation_unknown") as reservation_unknown,
    ):
        with pytest.raises(TimeoutError):
            _run(inference=fail)
    execution_unknown.assert_called_once()
    reservation_unknown.assert_called_once()


def test_encryption_or_persistence_failure_never_settles():
    async def infer():
        return _result()
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.claim_execution", return_value=CLAIM),
        patch("api.billing_execution.persist_encrypted_result", side_effect=RuntimeError("storage unavailable")),
        patch("api.billing_execution.mark_execution_unknown") as execution_unknown,
        patch("api.billing_execution.mark_reservation_unknown") as reservation_unknown,
        patch("api.billing_execution.settle_reservation") as settle,
    ):
        with pytest.raises(ResultPersistenceRequired):
            _run(inference=infer)
    execution_unknown.assert_called_once()
    reservation_unknown.assert_called_once()
    settle.assert_not_called()


def test_over_reservation_result_is_not_returned_to_caller():
    review = SettlementResult(RESERVATION.reservation_id, "review", None)
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.claim_execution", return_value=CLAIM),
        patch("api.billing_execution.persist_encrypted_result"),
        patch("api.billing_execution.settle_reservation", return_value=review),
    ):
        with pytest.raises(UsageReviewRequired):
            _run()
