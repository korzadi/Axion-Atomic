import pytest

from api.billing_budget import SUPPORTED_TOKENIZER_CONTRACT
from api.billing_preflight import (
    TokenizerVerificationRequired, prepare_billing_preflight,
)

MODEL = "atomic-code:16k-8k"


def args(**changes):
    values = dict(
        user_id="user-1", project_id="project-1",
        public_model="atomic-code", runtime_model=MODEL,
        expected_runtime_model=MODEL,
        final_messages=[
            {"role":"system","content":"system + retrieved context"},
            {"role":"user","content":"question"},
        ],
        temperature=0.2, max_output_tokens=128, context_window=16384,
        tokenizer_contract=SUPPORTED_TOKENIZER_CONTRACT,
        tokenizer_verified=True,
    )
    values.update(changes)
    return values


def test_preflight_fingerprints_exact_final_messages():
    result = prepare_billing_preflight(**args())
    changed = prepare_billing_preflight(**args(final_messages=[
        {"role":"system","content":"system + changed retrieved context"},
        {"role":"user","content":"question"},
    ]))
    assert result.payload_sha256 != changed.payload_sha256
    assert result.budget.reserved_credits > 0


def test_preflight_fails_closed_without_tokenizer_evidence():
    with pytest.raises(TokenizerVerificationRequired):
        prepare_billing_preflight(**args(tokenizer_verified=False))


def test_preflight_rejects_public_model_other_than_atomic_code():
    with pytest.raises(ValueError):
        prepare_billing_preflight(**args(public_model="other-model"))


def test_preflight_rejects_runtime_alias_mismatch():
    with pytest.raises(ValueError):
        prepare_billing_preflight(**args(runtime_model="another-model"))
