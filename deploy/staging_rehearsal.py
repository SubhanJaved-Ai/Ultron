"""Staging deployment rehearsal and verification test.

Validates the full production staging lifecycle:
1. Production environment configuration (OPENJARVIS_MULTI_USER=1, isolated config dir)
2. Health check and service readiness verification (/health, /api/auth/me)
3. Multi-user bootstrapping (First user is Admin, second user is standard User)
4. Authenticated Hologram directive execution
5. Unauthenticated rejection (HTTP 401)
6. SQLite database backup and point-in-time disaster recovery
7. Service restart recovery and credential persistence
8. Graceful shutdown simulation
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from openjarvis.auth.manager import UserManager, set_user_manager
from openjarvis.server.app import create_app


def run_staging_rehearsal():
    print("=" * 70)
    print("OPEN JARVIS / ULTRON — PRODUCTION STAGING REHEARSAL")
    print("=" * 70)

    staging_dir = Path(tempfile.mkdtemp(prefix="openjarvis_staging_"))
    backup_dir = Path(tempfile.mkdtemp(prefix="openjarvis_backup_"))

    print(f"[1/8] Initializing staging runtime environment: {staging_dir}")
    os.environ["OPENJARVIS_MULTI_USER"] = "1"
    os.environ["OPENJARVIS_CONFIG_DIR"] = str(staging_dir)

    db_path = staging_dir / "users.db"
    user_mgr = UserManager(db_path=db_path)
    set_user_manager(user_mgr)

    # 1. Startup & App creation
    print("[2/8] Spinning up application instance...")
    app = create_app()
    client = TestClient(app)

    # 2. Health check
    print("[3/8] Verifying health & readiness probes...")
    res_health = client.get("/health")
    assert res_health.status_code == 200, f"Health check failed: {res_health.text}"
    print(f"      -> GET /health: 200 OK ({res_health.json()})")

    # 3. Multi-User Registration & Privilege Guard
    print("[4/8] Testing multi-user bootstrapping & privilege guard...")
    # Admin registration (bootstrap)
    res_reg_admin = client.post(
        "/api/auth/register",
        json={"username": "sysadmin_ops", "password": "SecureAdmin123!"},
    )
    assert res_reg_admin.status_code == 200, f"Admin reg failed: {res_reg_admin.text}"
    admin_data = res_reg_admin.json()
    assert admin_data["user"]["role"] == "admin", f"Expected admin role, got {admin_data['user']['role']}"
    print("      -> First user 'sysadmin_ops' correctly bootstrapped as ADMIN.")

    # Standard user registration
    res_reg_user = client.post(
        "/api/auth/register",
        json={"username": "analyst_bob", "password": "AnalystPass123!"},
    )
    assert res_reg_user.status_code == 200, f"User reg failed: {res_reg_user.text}"
    user_data = res_reg_user.json()
    assert user_data["user"]["role"] == "user", f"Expected user role, got {user_data['user']['role']}"
    print("      -> Second user 'analyst_bob' strictly assigned USER role (privilege guard verified).")

    # 4. Authentication & Session Establishment
    print("[5/8] Testing authentication and token issuance...")
    res_login = client.post(
        "/api/auth/login",
        json={"username": "analyst_bob", "password": "AnalystPass123!"},
    )
    assert res_login.status_code == 200
    token = res_login.json()["token"]
    auth_header = {"Authorization": f"Bearer {token}"}
    print("      -> Session established; bearer token issued.")

    # 5. Protected Hologram Directive Execution
    print("[6/8] Testing protected Hologram directive execution...")
    # Clear session cookies to test completely unauthenticated request
    client.cookies.clear()
    res_unauth = client.post("/api/hologram/directive", json={"text": "hello"})
    assert res_unauth.status_code == 401, f"Expected 401 for unauth, got {res_unauth.status_code}"
    print("      -> Unauthenticated directive call correctly rejected: 401 Unauthorized.")

    # Authenticated directive execution via Bearer token header
    res_auth = client.post(
        "/api/hologram/directive",
        headers=auth_header,
        json={"directive": "What is the system status?"},
    )
    assert res_auth.status_code == 200, f"Authenticated directive failed: {res_auth.text}"
    resp_payload = res_auth.json()
    assert "reply" in resp_payload, f"Expected reply in directive payload, got {resp_payload}"
    print(f"      -> Authenticated directive executed successfully: {resp_payload['reply'][:50]}...")

    # 6. Database Backup & Disaster Recovery
    print("[7/8] Testing online database backup and disaster recovery restore...")
    backup_file = backup_dir / "users_snapshot.db"

    # Perform hot backup using SQLite online backup API
    src_conn = sqlite3.connect(str(db_path))
    dst_conn = sqlite3.connect(str(backup_file))
    try:
        src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()
    print(f"      -> Hot backup snapshot saved ({backup_file.stat().st_size} bytes).")

    # Close connections and client before file replacement
    client.close()
    user_mgr.close()
    set_user_manager(None)
    import gc
    gc.collect()

    # Simulate disaster: wipe original staging db
    db_path.unlink()
    assert not db_path.exists()
    print("      -> [Disaster Injected] Primary database deleted.")

    # Restore from backup
    shutil.copyfile(backup_file, db_path)
    assert db_path.exists()
    print("      -> Point-in-time recovery completed from backup snapshot.")

    # Verify restored database allows user login
    restored_mgr = UserManager(db_path=db_path)
    set_user_manager(restored_mgr)
    restored_user = restored_mgr.authenticate("analyst_bob", "AnalystPass123!")
    assert restored_user is not None
    assert restored_user.username == "analyst_bob"
    print("      -> Restored user credentials verified successfully.")

    # 7. Restart Recovery
    print("[8/8] Testing application restart recovery...")
    # Instantiate new app instance with restored data
    app_restarted = create_app()
    client_restarted = TestClient(app_restarted)

    res_relogin = client_restarted.post(
        "/api/auth/login",
        json={"username": "analyst_bob", "password": "AnalystPass123!"},
    )
    assert res_relogin.status_code == 200
    new_token = res_relogin.json()["token"]
    res_me = client_restarted.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert res_me.status_code == 200
    assert res_me.json()["user"]["username"] == "analyst_bob"
    print("      -> App restart recovery confirmed: user authenticated, session valid.")

    # Cleanup staging connections and directories
    client_restarted.close()
    set_user_manager(None)
    gc.collect()
    shutil.rmtree(staging_dir, ignore_errors=True)
    shutil.rmtree(backup_dir, ignore_errors=True)

    print("=" * 70)
    print("STAGING REHEARSAL RESULT: ALL 8/8 CHECKS PASSED (100% SUCCESS)")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_staging_rehearsal()
    sys.exit(0 if success else 1)
