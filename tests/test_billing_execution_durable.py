import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.billing_budget import InferenceBudget
from api.billing_execution_store import ExecutionClaim, EncryptedExecutionResult
from api.billing_reservations import ReservationResult, SettlementResult
from api.billing_execution_durable import (
    DurableExecutionRecoveryRequired,
    execute_durable_reserved_inference,
)

MODEL = "atomic-code:16k-8k"
BUDGET = InferenceBudget(
    policy_version="atomic-code-budget-v1", runtime_model=MODEL,
    tokenizer_contract="qwen2_byte_fallback", input_tokens_upper_bound=80,
    output_tokens_upper_bound=20, input_weight=1, output_weight=1,
    reserved_credits=100, context_window=16384,
)
RES = ReservationResult("00000000-0000-0000-0000-000000000001", "held", 100)
SETTLED = SettlementResult(RES.reservation_id, "settled", 20)


def result():
    return SimpleNamespace(
        requested_model=MODEL, returned_model=MODEL, done=True,
        usage_source="ollama_response", prompt_eval_count=12, eval_count=8,
    )


class Cipher:
    def encrypt(self, plaintext, **ctx):
        return SimpleNamespace(ciphertext=b"enc:"+plaintext, nonce=b"n"*12, key_id="k1")
    def decrypt(self, encrypted, **ctx):
        assert encrypted.ciphertext.startswith(b"enc:")
        return encrypted.ciphertext[4:]


def call(**kwargs):
    return asyncio.run(execute_durable_reserved_inference(
        engine=object(), user_id="u", project_id="p",
        request_id="00000000-0000-0000-0000-000000000002",
        idempotency_key="key", payload_sha256="a"*64,
        budget=BUDGET, expected_runtime_model=MODEL,
        reservation_expires_at=datetime.now(timezone.utc)+timedelta(minutes=5),
        cipher=Cipher(), serialize_result=lambda r: b"serialized",
        deserialize_result=kwargs.pop("deserialize_result", lambda b: result()), **kwargs,
    ))


def test_new_execution_persists_ciphertext_before_settlement():
    order=[]
    async def infer():
        order.append("inference")
        return result()
    def persist(**kw):
        order.append("persist")
        return EncryptedExecutionResult("00000000-0000-0000-0000-000000000003", kw["ciphertext"], kw["nonce"], kw["key_id"], "digest")
    with (
        patch("api.billing_execution_durable.reserve_credits", return_value=RES),
        patch("api.billing_execution_durable.claim_execution", return_value=ExecutionClaim("00000000-0000-0000-0000-000000000003","started",True)),
        patch("api.billing_execution_durable.persist_encrypted_result", side_effect=persist),
        patch("api.billing_execution_durable.settle_reservation", side_effect=lambda **kw: (order.append("settle"), SETTLED)[1]),
    ):
        outcome=call(inference_call=infer)
    assert order == ["inference","persist","settle"]
    assert outcome.recovered is False


def test_completed_execution_recovers_without_inference_and_settles():
    inference=AsyncMock()
    stored=EncryptedExecutionResult("00000000-0000-0000-0000-000000000003",b"enc:serialized",b"n"*12,"k1","digest")
    with (
        patch("api.billing_execution_durable.reserve_credits",return_value=RES),
        patch("api.billing_execution_durable.claim_execution",return_value=ExecutionClaim(stored.execution_id,"completed",False)),
        patch("api.billing_execution_durable.load_encrypted_result",return_value=stored),
        patch("api.billing_execution_durable.settle_reservation",return_value=SETTLED),
    ):
        outcome=call(inference_call=inference)
    inference.assert_not_awaited()
    assert outcome.recovered is True
    assert outcome.settlement.state == "settled"


@pytest.mark.parametrize("state",["started","unknown","review"])
def test_noncompleted_claim_never_reexecutes(state):
    inference=AsyncMock()
    with (
        patch("api.billing_execution_durable.reserve_credits",return_value=RES),
        patch("api.billing_execution_durable.claim_execution",return_value=ExecutionClaim("00000000-0000-0000-0000-000000000003",state,False)),
    ):
        with pytest.raises(DurableExecutionRecoveryRequired):
            call(inference_call=inference)
    inference.assert_not_awaited()


def test_recovered_envelope_must_match_reserved_policy_snapshot():
    inference = AsyncMock()
    stored = EncryptedExecutionResult(
        "00000000-0000-0000-0000-000000000003",
        b"enc:serialized", b"n"*12, "k1", "digest",
    )
    mismatched = SimpleNamespace(
        requested_model=MODEL, returned_model=MODEL, done=True,
        usage_source="ollama_response", prompt_eval_count=12, eval_count=8,
        policy_version="different-policy", input_weight=1, output_weight=1,
        actual_credits=20,
    )
    with (
        patch("api.billing_execution_durable.reserve_credits", return_value=RES),
        patch("api.billing_execution_durable.claim_execution", return_value=ExecutionClaim(stored.execution_id, "completed", False)),
        patch("api.billing_execution_durable.load_encrypted_result", return_value=stored),
    ):
        with pytest.raises(Exception, match="política del resultado cifrado"):
            call(inference_call=inference, deserialize_result=lambda _: mismatched)
    inference.assert_not_awaited()


def test_recovered_envelope_must_match_saved_credit_calculation():
    inference = AsyncMock()
    stored = EncryptedExecutionResult(
        "00000000-0000-0000-0000-000000000003",
        b"enc:serialized", b"n"*12, "k1", "digest",
    )
    mismatched = SimpleNamespace(
        requested_model=MODEL, returned_model=MODEL, done=True,
        usage_source="ollama_response", prompt_eval_count=12, eval_count=8,
        policy_version="atomic-code-budget-v1", input_weight=1, output_weight=1,
        actual_credits=999,
    )
    with (
        patch("api.billing_execution_durable.reserve_credits", return_value=RES),
        patch("api.billing_execution_durable.claim_execution", return_value=ExecutionClaim(stored.execution_id, "completed", False)),
        patch("api.billing_execution_durable.load_encrypted_result", return_value=stored),
    ):
        with pytest.raises(Exception, match="créditos guardados"):
            call(inference_call=inference, deserialize_result=lambda _: mismatched)
    inference.assert_not_awaited()
