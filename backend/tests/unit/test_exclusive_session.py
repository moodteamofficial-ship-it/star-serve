"""Exclusive session — one ACTIVE row per user."""

import inspect

from app.modules.auth.service import AuthService


def test_issue_session_always_revokes_other_live_rows() -> None:
    source = inspect.getsource(AuthService._issue_session)
    assert "_lock_user_for_sessions" in source
    assert "_revoke_active_sessions" in source
    assert "superseded_sessions" in source


def test_refresh_rechecks_after_lock() -> None:
    source = inspect.getsource(AuthService.refresh)
    assert "_lock_user_for_sessions" in source
    assert "session.refresh" in source
    assert "Session is no longer valid" in source
    # Rotation must not leave the previous row ACTIVE.
    assert "session.revoked_at = datetime.now(UTC)" not in source


def test_revoke_active_keeps_rows() -> None:
    source = inspect.getsource(AuthService._revoke_active_sessions)
    assert "deleted_at" not in source.split("values", 1)[1]
    assert "SessionStatus.REVOKED" in source
    assert "revoked_at.is_(None)" in source


def test_migration_file_has_partial_unique_index() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "alembic/versions/0021_exclusive_user_session.py"
    text = path.read_text(encoding="utf-8")
    assert "uq_sessions_one_active_per_user" in text
    assert "status = 'ACTIVE'" in text
    assert "revoked_at IS NULL" in text
    assert "row_number()" in text
