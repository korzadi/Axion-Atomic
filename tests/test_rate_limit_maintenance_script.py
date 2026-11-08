from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from scripts import prune_expired_rate_limits as maintenance


NOW = datetime(2026, 11, 8, 16, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("size", [0, -1, 10001, True, 1.5, "10", None])
def test_cleanup_rejects_invalid_batch_size_before_database_access(size):
    target = Mock()
    with pytest.raises(ValueError, match="batch-size"):
        maintenance.run_cleanup(target_engine=target, batch_size=size)
    target.connect.assert_not_called()


def test_dry_run_only_counts_expired_buckets_and_never_calls_delete():
    result = Mock()
    result.scalar_one.return_value = 7
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.execute.return_value = result
    target = Mock()
    target.connect.return_value = connection

    with patch.object(maintenance, "prune_expired_rate_limits") as prune:
        outcome = maintenance.run_cleanup(
            target_engine=target, apply=False, batch_size=25, now=NOW,
        )

    assert outcome == {"mode": "dry-run", "expired": 7, "deleted": 0}
    connection.execute.assert_called_once()
    assert "SELECT COUNT(*)" in str(connection.execute.call_args.args[0])
    assert connection.execute.call_args.args[1] == {"now": NOW}
    prune.assert_not_called()


def test_apply_deletes_only_one_explicitly_bounded_batch():
    target = Mock()
    with patch.object(maintenance, "prune_expired_rate_limits", return_value=3) as prune:
        outcome = maintenance.run_cleanup(
            target_engine=target, apply=True, batch_size=3, now=NOW,
        )

    assert outcome == {"mode": "apply", "expired": 3, "deleted": 3}
    prune.assert_called_once_with(engine=target, now=NOW, batch_size=3)
    target.connect.assert_not_called()


def test_cleanup_rejects_naive_datetime_before_database_access():
    target = Mock()
    with pytest.raises(ValueError, match="zona horaria"):
        maintenance.run_cleanup(
            target_engine=target, now=datetime(2026, 11, 8, 16, 0),
        )
    target.connect.assert_not_called()
