import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.billing_budget import InferenceBudget
from api.billing_execution import (
    DuplicateExecution,
    ModelExecutionMismatch,
    UsageReviewRequired,
    execute_reserved_inference,
)
from api.billing_policy import UsageUnavailable
from api.billing_reservations import ReservationResult, SettlementResult


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
SETTLED = SettlementResult(RESERVATION.reservation_id, "settled", 20)


def _result(**overrides):
    values = dict(
        requested_model=MODEL, returned_model=MODEL, done=True,
        prompt_eval_count=12, eval_count=8, usage_source="ollama_response",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _run(result=None, *, reservation=None, inference=None, settlement=None):
    return asyncio.run(execute_reserved_inference(
        engine=object(), user_id="user-1", project_id="project-1",
        request_id="00000000-0000-0000-0000-000000000002",
        idempotency_key="request-key-1", payload_sha256="a" * 64,
        budget=BUDGET, expected_runtime_model=MODEL,
        inference_call=inference or AsyncMock(return_value=result or _result()),
        reservation_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    ))


def test_reserves_before_inference_and_settles_actual_usage():
    order = []
    async def infer():
        order.append("infer")
        return _result()

    with (
        patch("api.billing_execution.reserve_credits", side_effect=lambda **kw: (
            order.append("reserve"), RESERVATION
        )[1]) as reserve,
        patch("api.billing_execution.settle_reservation", return_value=SETTLED) as settle,
    ):
        result = _run(inference=infer)

    assert order == ["reserve", "infer"]
    assert reserve.call_args.kwargs["required_credits"] == 150
    assert settle.call_args.kwargs["actual_credits"] == 20
    assert result.settlement.state == "settled"


def test_idempotent_reservation_never_repeats_inference():
    inference = AsyncMock(return_value=_result())
    repeated = ReservationResult(RESERVATION.reservation_id, "held", 150, True)
    with patch("api.billing_execution.reserve_credits", return_value=repeated):
        with pytest.raises(DuplicateExecution):
            _run(inference=inference)
    inference.assert_not_awaited()


@pytest.mark.parametrize("bad", [
    _result(returned_model="other-model"),
    _result(done=False),
])
def test_model_mismatch_or_incomplete_execution_keeps_reservation(bad):
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.mark_reservation_unknown") as unknown,
    ):
        with pytest.raises(ModelExecutionMismatch):
            _run(result=bad)
    unknown.assert_called_once()


def test_missing_provider_counters_keep_reservation_unknown():
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.mark_reservation_unknown") as unknown,
    ):
        with pytest.raises(UsageUnavailable):
            _run(result=_result(prompt_eval_count=None, usage_source="unavailable"))
    unknown.assert_called_once()


def test_inference_exception_keeps_reservation_unknown():
    async def fail():
        raise TimeoutError("provider timeout")
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.mark_reservation_unknown") as unknown,
    ):
        with pytest.raises(TimeoutError):
            _run(inference=fail)
    unknown.assert_called_once()


def test_over_reservation_result_is_not_returned_to_caller():
    review = SettlementResult(RESERVATION.reservation_id, "review", None)
    with (
        patch("api.billing_execution.reserve_credits", return_value=RESERVATION),
        patch("api.billing_execution.settle_reservation", return_value=review),
    ):
        with pytest.raises(UsageReviewRequired):
            _run()
