"""Tests for UserManager, crypto, session lifecycles, and preferences."""

import pytest

from openjarvis.auth import (
    Role,
    UserManager,
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hashing():
    pwd = "SecretPassword123!"
    h1, s1 = hash_password(pwd)
    assert verify_password(pwd, h1, s1)
    assert not verify_password("WrongPassword", h1, s1)

    # Different salts produce different hashes
    h2, s2 = hash_password(pwd)
    assert s1 != s2
    assert h1 != h2
    assert verify_password(pwd, h2, s2)


def test_session_token_hashing():
    t1 = generate_session_token()
    assert t1.startswith("oj_usr_")
    assert len(t1) > 20
    ht1 = hash_token(t1)
    assert len(ht1) == 64  # sha256 hex
    assert ht1 == hash_token(t1)


def test_user_manager_registration_and_auth(tmp_path):
    db_file = tmp_path / "test_users.db"
    mgr = UserManager(db_path=db_file)

    # First registered user becomes admin
    u1 = mgr.register("admin_user", "AdminPass1234")
    assert u1.username == "admin_user"
    assert u1.role == Role.ADMIN.value
    assert u1.is_admin()

    # Second user is standard user
    u2 = mgr.register("beta_user", "BetaPass1234")
    assert u2.username == "beta_user"
    assert u2.role == Role.USER.value
    assert not u2.is_admin()

    # Duplicate username raises ValueError
    with pytest.raises(ValueError):
        mgr.register("beta_user", "AnotherPass1234")

    # Short password raises ValueError
    with pytest.raises(ValueError):
        mgr.register("gamma_user", "short")

    # Authentication tests
    auth1 = mgr.authenticate("admin_user", "AdminPass1234")
    assert auth1 is not None
    assert auth1.id == u1.id

    auth_bad = mgr.authenticate("admin_user", "WrongPassword")
    assert auth_bad is None

    auth_nonexistent = mgr.authenticate("nobody", "WrongPassword")
    assert auth_nonexistent is None

    mgr.close()


def test_user_manager_session_lifecycle(tmp_path):
    db_file = tmp_path / "test_users.db"
    mgr = UserManager(db_path=db_file)

    u = mgr.register("alice", "AlicePass1234")
    token = mgr.create_session(u.id, ttl_seconds=3600)
    assert token.startswith("oj_usr_")

    # Validate active session
    val_user = mgr.validate_session(token)
    assert val_user is not None
    assert val_user.id == u.id
    assert val_user.username == "alice"

    # Revoke single session
    assert mgr.revoke_session(token)
    assert mgr.validate_session(token) is None

    # Test multi-session revocation
    token2 = mgr.create_session(u.id, ttl_seconds=3600)
    token3 = mgr.create_session(u.id, ttl_seconds=3600)
    assert mgr.validate_session(token2) is not None
    assert mgr.validate_session(token3) is not None

    mgr.revoke_all_user_sessions(u.id)
    assert mgr.validate_session(token2) is None
    assert mgr.validate_session(token3) is None

    # Test expired session
    expired_token = mgr.create_session(u.id, ttl_seconds=-10)
    assert mgr.validate_session(expired_token) is None

    mgr.close()


def test_user_manager_preferences_isolation(tmp_path):
    db_file = tmp_path / "test_users.db"
    mgr = UserManager(db_path=db_file)

    u1 = mgr.register("user_one", "PassOne1234")
    u2 = mgr.register("user_two", "PassTwo1234")

    mgr.set_preference(u1.id, "preferred_address", "Supreme Leader")
    mgr.set_preference(u2.id, "preferred_address", "General Beta")

    assert mgr.get_preference(u1.id, "preferred_address") == "Supreme Leader"
    assert mgr.get_preference(u2.id, "preferred_address") == "General Beta"

    # Account deletion cleans up user and preferences
    assert mgr.delete_user(u1.id)
    assert mgr.get_user(u1.id) is None
    assert mgr.get_preference(u1.id, "preferred_address") is None
    # User two remains untouched
    assert mgr.get_preference(u2.id, "preferred_address") == "General Beta"

    mgr.close()
