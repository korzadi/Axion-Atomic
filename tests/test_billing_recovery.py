from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from api.billing_execution_store import EncryptedExecutionResult
from api.billing_reservations import SettlementResult
from api.billing_recovery import recover_completed_billing_executions


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, params):
        return self

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeEngine:
    def __init__(self, rows):
        self.rows = rows

    @contextmanager
    def connect(self):
        yield FakeConnection(self.rows)


class FakeCipher:
    def decrypt(self, encrypted, **context):
        assert encrypted.ciphertext == b"ciphertext"
        assert context["execution_id"] == "execution-1"
        return b"verified-envelope"


def _candidate(**overrides):
    value = {
        "reservation_id": "reservation-1",
        "user_id": "user-1",
        "policy_version": "policy-v1",
        "execution_id": "execution-1",
    }
    value.update(overrides)
    return value


def _stored():
    return EncryptedExecutionResult(
        "execution-1", b"ciphertext", b"n" * 12, "key-v1", "digest"
    )


def test_recovery_settles_completed_ciphertext_without_inference():
    engine = FakeEngine([_candidate()])
    with (
        patch("api.billing_recovery._claim_attempt", return_value=1),
        patch("api.billing_recovery._finish_attempt") as finish,
        patch("api.billing_recovery.load_encrypted_result", return_value=_stored()),
        patch("api.billing_recovery.parse_execution_envelope",
              return_value=SimpleNamespace(policy_version="policy-v1", credits=20)),
        patch("api.billing_recovery.settle_reservation",
              return_value=SettlementResult("reservation-1", "settled", 20)) as settle,
    ):
        batch = recover_completed_billing_executions(
            engine=engine, cipher=FakeCipher(), limit=10,
        )

    settle.assert_called_once_with(
        engine=engine, user_id="user-1", reservation_id="reservation-1",
        actual_credits=20,
    )
    finish.assert_called_once_with(
        engine, "execution-1", attempt=1, error_code=None, settled=True,
    )
    assert batch.examined == 1
    assert batch.settled == 1
    assert batch.review == 0
    assert batch.failed == 0


def test_recovery_refuses_policy_mismatch_and_schedules_backoff():
    engine = FakeEngine([_candidate()])
    with (
        patch("api.billing_recovery._claim_attempt", return_value=3),
        patch("api.billing_recovery._finish_attempt") as finish,
        patch("api.billing_recovery.load_encrypted_result", return_value=_stored()),
        patch("api.billing_recovery.parse_execution_envelope",
              return_value=SimpleNamespace(policy_version="wrong-policy", credits=20)),
        patch("api.billing_recovery.settle_reservation") as settle,
    ):
        batch = recover_completed_billing_executions(
            engine=engine, cipher=FakeCipher(),
        )

    settle.assert_not_called()
    finish.assert_called_once_with(
        engine, "execution-1", attempt=3, error_code="ValueError", settled=False,
    )
    assert batch.failed == 1
    assert batch.items[0].state == "failed"
    assert batch.items[0].detail == "ValueError"


def test_recovery_marks_over_reserved_usage_for_review():
    engine = FakeEngine([_candidate()])
    with (
        patch("api.billing_recovery._claim_attempt", return_value=1),
        patch("api.billing_recovery._finish_attempt") as finish,
        patch("api.billing_recovery.load_encrypted_result", return_value=_stored()),
        patch("api.billing_recovery.parse_execution_envelope",
              return_value=SimpleNamespace(policy_version="policy-v1", credits=999)),
        patch("api.billing_recovery.settle_reservation",
              return_value=SettlementResult("reservation-1", "review", None)),
    ):
        batch = recover_completed_billing_executions(
            engine=engine, cipher=FakeCipher(),
        )

    finish.assert_called_once_with(
        engine, "execution-1", attempt=1,
        error_code="UsageReviewRequired", settled=False,
    )
    assert batch.review == 1
    assert batch.settled == 0
    assert batch.items[0].state == "review"


def test_recovery_skips_execution_claimed_by_another_worker():
    engine = FakeEngine([_candidate()])
    with (
        patch("api.billing_recovery._claim_attempt", return_value=None),
        patch("api.billing_recovery.load_encrypted_result") as load,
        patch("api.billing_recovery.settle_reservation") as settle,
    ):
        batch = recover_completed_billing_executions(
            engine=engine, cipher=FakeCipher(),
        )

    load.assert_not_called()
    settle.assert_not_called()
    assert batch.examined == 0
    assert batch.skipped == 1


def test_recovery_requires_bounded_batch_size():
    engine = FakeEngine([])
    for invalid in (0, -1, 1001, True, 1.5):
        try:
            recover_completed_billing_executions(engine=engine, cipher=FakeCipher(), limit=invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"limit {invalid!r} should be rejected")
