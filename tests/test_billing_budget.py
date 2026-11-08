import pytest

from api.billing_budget import (
    ContextBudgetExceeded,
    SUPPORTED_TOKENIZER_CONTRACT,
    UnsupportedTokenizerContract,
    calculate_preflight_budget,
)


MODEL = "atomic-code:16k-8k"


def _budget(messages=None, **overrides):
    args = {
        "messages": messages or [
            {"role": "system", "content": "instrucciones y RAG"},
            {"role": "user", "content": "print('hola')"},
        ],
        "max_output_tokens": 512,
        "context_window": 16384,
        "runtime_model": MODEL,
        "expected_runtime_model": MODEL,
        "tokenizer_contract": SUPPORTED_TOKENIZER_CONTRACT,
    }
    args.update(overrides)
    return calculate_preflight_budget(**args)


def test_budget_includes_system_history_and_retrieved_context():
    messages = [
        {"role": "system", "content": "S" * 1000 + " RAG " + "x" * 500},
        {"role": "user", "content": "U" * 100},
        {"role": "assistant", "content": "A" * 200},
        {"role": "user", "content": "última consulta"},
    ]
    budget = _budget(messages=messages)
    expected = sum(len(m["content"].encode("utf-8")) + 32 for m in messages) + 256
    assert budget.input_tokens_upper_bound == expected
    assert budget.reserved_credits == expected + 512
    assert budget.output_tokens_upper_bound == 512


def test_utf8_byte_bound_counts_multibyte_text_conservatively():
    budget = _budget(messages=[{"role": "user", "content": "á🙂"}])
    assert budget.input_tokens_upper_bound == len("á🙂".encode("utf-8")) + 32 + 256


def test_rejects_prompt_plus_max_output_over_context_window():
    with pytest.raises(ContextBudgetExceeded):
        _budget(
            messages=[{"role": "system", "content": "x" * 16000}],
            max_output_tokens=512,
            context_window=16384,
        )


def test_rejects_output_larger_than_context_window():
    with pytest.raises(ContextBudgetExceeded):
        _budget(max_output_tokens=16385, context_window=16384)


def test_rejects_unpinned_runtime_model():
    with pytest.raises(ValueError):
        _budget(runtime_model="another-model")


def test_rejects_unknown_tokenizer_contract():
    with pytest.raises(UnsupportedTokenizerContract):
        _budget(tokenizer_contract="unknown-tokenizer")


def test_applies_versioned_input_and_output_weights_to_reservation():
    budget = _budget(input_weight=2, output_weight=3)
    assert budget.reserved_credits == (
        budget.input_tokens_upper_bound * 2 + budget.output_tokens_upper_bound * 3
    )


@pytest.mark.parametrize("bad", [True, -1, 1.5, "12"])
def test_rejects_invalid_limits_and_weights(bad):
    with pytest.raises(ValueError):
        _budget(max_output_tokens=bad)


def test_rejects_invalid_message_shape():
    with pytest.raises(ValueError):
        _budget(messages=[{"role": "tool", "content": "result"}])


def test_fractional_weights_reserve_ceiling_credits_exactly():
    from decimal import Decimal, ROUND_CEILING

    budget = _budget(input_weight=0.01, output_weight=0.01)
    expected = int(
        (
            Decimal(budget.input_tokens_upper_bound) * Decimal("0.01")
            + Decimal(budget.output_tokens_upper_bound) * Decimal("0.01")
        ).to_integral_value(rounding=ROUND_CEILING)
    )
    assert budget.reserved_credits == expected


def test_hundred_tokens_cost_exactly_one_credit_with_approved_weights():
    budget = _budget(input_weight=0.01, output_weight=0.01)
    assert budget.reserved_credits == (
        (budget.input_tokens_upper_bound + budget.output_tokens_upper_bound + 99) // 100
    )
