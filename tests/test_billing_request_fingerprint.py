import pytest
from api.billing_request_fingerprint import (
    BillingRequestFingerprintError, billing_request_fingerprint,
)


def base(**changes):
    values = dict(
        user_id="u1", project_id="p1", model="atomic-code",
        messages=[{"role":"system","content":"sys"},{"role":"user","content":"hola"}],
        temperature=0.2, max_output_tokens=1024, policy_version="v1",
    )
    values.update(changes)
    return billing_request_fingerprint(**values)


def test_fingerprint_is_deterministic():
    assert base() == base()


@pytest.mark.parametrize("change", [
    {"user_id":"u2"}, {"project_id":"p2"}, {"model":"other"},
    {"messages":[{"role":"user","content":"different"}]},
    {"temperature":0.3}, {"max_output_tokens":512}, {"policy_version":"v2"},
])
def test_fingerprint_binds_all_billing_relevant_inputs(change):
    assert base() != base(**change)


def test_fingerprint_rejects_extra_message_fields():
    with pytest.raises(BillingRequestFingerprintError):
        base(messages=[{"role":"user","content":"x","private":"no"}])


def test_fingerprint_rejects_nan_temperature():
    with pytest.raises(BillingRequestFingerprintError):
        base(temperature=float("nan"))
