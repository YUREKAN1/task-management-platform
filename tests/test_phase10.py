"""
Phase 10 — Testing & Test Quality Tests.

Covers:
- TQ-1: User input validation (empty name / empty password rejected with 422)
- Empty body PATCH /users/me behaves as a clean no-op (200 OK)
- Global admin can access and list project tasks across teams
- Audit log API response metadata contract (metadata_ -> metadata alias serialization)
- Transaction integrity on failed task creation (no orphan DB rows or audit logs)
"""
import pytest
from uuid import uuid4

from app.models.enums import GlobalRole, AuditAction
from app.models.user import User
from app.models.task import Task
from app.models.audit_log import AuditLog


# ─── Helpers ─────────────────────────────────────────────────────────────────

def register_and_login(client, email, name=None, password="password123"):
    name = name or email.split("@")[0]
    client.post("/auth/register", json={"name": name, "email": email, "password": password})
    res = client.post("/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_admin(db_session, email):
    user = db_session.query(User).filter(User.email == email).first()
    user.global_role = GlobalRole.ADMIN
    db_session.commit()


# ─── User Registration Validation (TQ-1) ─────────────────────────────────────

class TestUserRegistrationValidation:

    def test_register_empty_name_returns_422(self, client):
        res = client.post("/auth/register", json={
            "name": "",
            "email": "p10_noname@example.com",
            "password": "validpassword123",
        })
        assert res.status_code == 422

    def test_register_empty_password_returns_422(self, client):
        res = client.post("/auth/register", json={
            "name": "Valid Name",
            "email": "p10_nopass@example.com",
            "password": "",
        })
        assert res.status_code == 422

    def test_update_user_empty_name_returns_422(self, client):
        token = register_and_login(client, "p10_upd_name@example.com")
        res = client.patch("/users/me", headers=auth(token), json={"name": ""})
        assert res.status_code == 422

    def test_update_user_empty_body_noop(self, client):
        token = register_and_login(client, "p10_noop@example.com", name="Original Name")
        res = client.patch("/users/me", headers=auth(token), json={})
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Original Name"
        assert data["email"] == "p10_noop@example.com"


# ─── Admin Cross-Team Task Authorization ────────────────────────────────────

class TestAdminCrossTeamTaskAccess:

    def test_global_admin_can_access_any_project_task(self, client, db_session):
        # 1. Manager creates team, project, and task
        mgr_token = register_and_login(client, "p10_mgr@example.com")
        team = client.post("/teams", headers=auth(mgr_token), json={"name": "P10 Team"}).json()
        project = client.post(
            f"/teams/{team['id']}/projects",
            headers=auth(mgr_token),
            json={"name": "P10 Project"},
        ).json()
        task = client.post(
            f"/projects/{project['id']}/tasks",
            headers=auth(mgr_token),
            json={"title": "P10 Admin Access Task"},
        ).json()

        # 2. Register separate admin user who is NOT a member of the team
        admin_token = register_and_login(client, "p10_admin@example.com")
        make_admin(db_session, "p10_admin@example.com")

        # 3. Admin can retrieve single project task
        res_get = client.get(f"/tasks/{task['id']}", headers=auth(admin_token))
        assert res_get.status_code == 200
        assert res_get.json()["id"] == task["id"]

        # 4. Admin can list tasks in the project
        res_list = client.get(f"/projects/{project['id']}/tasks", headers=auth(admin_token))
        assert res_list.status_code == 200
        items = res_list.json()["items"]
        assert any(t["id"] == task["id"] for t in items)


# ─── API Contract: Audit Log Metadata Field Serialization ────────────────────

class TestAuditLogMetadataContract:

    def test_audit_log_api_response_metadata_serialization(self, client, db_session):
        # Admin performs an update which writes structured metadata
        admin_token = register_and_login(client, "p10_audit_admin@example.com", name="Initial")
        make_admin(db_session, "p10_audit_admin@example.com")

        client.patch("/users/me", headers=auth(admin_token), json={"name": "Serialized Metadata Check"})

        # Admin fetches audit log via HTTP API
        res = client.get("/audit-logs?action=USER_UPDATED", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        latest_item = data["items"][0]

        # Verify API response contract exposes 'metadata' (not internal 'metadata_')
        assert "metadata" in latest_item
        assert latest_item["metadata"] is not None
        assert latest_item["metadata"].get("name") == "Serialized Metadata Check"


# ─── Transaction Integrity ───────────────────────────────────────────────────

class TestTransactionIntegrity:

    def test_failed_project_task_creation_leaves_no_database_artifacts(self, client, db_session):
        mgr_token = register_and_login(client, "p10_tx_mgr@example.com")
        team = client.post("/teams", headers=auth(mgr_token), json={"name": "Tx Team"}).json()
        project = client.post(
            f"/teams/{team['id']}/projects",
            headers=auth(mgr_token),
            json={"name": "Tx Project"},
        ).json()

        # Attempt to assign to nonexistent user -> 404
        fake_assignee = uuid4()
        res = client.post(
            f"/projects/{project['id']}/tasks",
            headers=auth(mgr_token),
            json={"title": "Should Never Exist", "assigned_to": str(fake_assignee)},
        )
        assert res.status_code == 404

        # Confirm no Task was created in DB
        db_task = db_session.query(Task).filter(Task.title == "Should Never Exist").first()
        assert db_task is None

        # Confirm no TASK_CREATED audit log was committed
        db_log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TASK_CREATED,
            AuditLog.description.contains("Should Never Exist"),
        ).first()
        assert db_log is None
