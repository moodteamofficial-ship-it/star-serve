"""Unit tests for progressive login lockout schedule."""

from datetime import UTC, datetime, timedelta

from app.modules.auth.lockout import (
    ATTEMPTS_BEFORE_FIRST_LOCK,
    ATTEMPTS_BEFORE_LATER_LOCK,
    LOCK_MINUTES_SCHEDULE,
    attempts_required_for_level,
    device_fingerprint,
    lock_minutes_for_level,
    remaining_lock_seconds,
)


def test_first_lock_needs_three_attempts() -> None:
    assert attempts_required_for_level(0) == ATTEMPTS_BEFORE_FIRST_LOCK == 3


def test_later_locks_need_two_attempts() -> None:
    for level in range(1, 8):
        assert attempts_required_for_level(level) == ATTEMPTS_BEFORE_LATER_LOCK == 2


def test_email_global_lock_needs_more_attempts() -> None:
    from app.modules.auth.lockout import (
        EMAIL_GLOBAL_ATTEMPTS_FIRST,
        EMAIL_GLOBAL_ATTEMPTS_LATER,
    )

    assert attempts_required_for_level(0, email_global=True) == EMAIL_GLOBAL_ATTEMPTS_FIRST == 15
    assert attempts_required_for_level(1, email_global=True) == EMAIL_GLOBAL_ATTEMPTS_LATER == 8


def test_lock_minutes_progressive_schedule() -> None:
    assert lock_minutes_for_level(0) == 3
    assert lock_minutes_for_level(1) == 10
    assert lock_minutes_for_level(2) == 30
    assert lock_minutes_for_level(3) == 60
    assert lock_minutes_for_level(100) == LOCK_MINUTES_SCHEDULE[-1]


def test_device_fingerprint_stable_and_sensitive() -> None:
    a = device_fingerprint("1.2.3.4", "Mozilla/5.0", "device-a")
    b = device_fingerprint("1.2.3.4", "Mozilla/5.0", "device-a")
    c = device_fingerprint("1.2.3.4", "Mozilla/5.0", "device-b")
    d = device_fingerprint("9.9.9.9", "Mozilla/5.0", "device-a")
    assert a == b
    assert a != c
    assert a != d
    assert len(a) == 64


def test_remaining_lock_seconds() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    until = now + timedelta(minutes=3)
    assert remaining_lock_seconds(until, now=now) == 180
    assert remaining_lock_seconds(None, now=now) == 0
    assert remaining_lock_seconds(now - timedelta(seconds=1), now=now) == 0
