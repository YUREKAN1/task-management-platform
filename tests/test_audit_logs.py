"""
Phase 8 – Audit Logging Tests

Comprehensive tests for:
- Audit log creation across all 17 actions (User, Team, Project, Task)
- Actor security and sensitive data protection
- Transaction consistency (no audit log on failed mutations)
- Role-based access control (Admin, Team Manager, Normal User)
- Team-scoped visibility and isolation
- Database-side filtering and pagination
"""
import pytest
from datetime import datetime, timedelta
from uuid import UUID

from app.models.enums import GlobalRole, TeamRole, AuditAction
from app.models.user import User
from app.models.audit_log import AuditLog


# ─── Helpers ─────────────────────────────────────────────────────────────────

def register_and_login(client, email, password="password123"):
    client.post("/auth/register", json={"name": email.split("@")[0], "email": email, "password": password})
    return client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def me(client, token):
    return client.get("/users/me", headers=auth(token)).json()


def make_admin(db_session, email):
    user = db_session.query(User).filter(User.email == email).first()
    user.global_role = GlobalRole.ADMIN
    db_session.commit()


def iso(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def audit_setup(client, db_session):
    """
    Sets up:
    - admin user (global_role = ADMIN)
    - manager_a (creates and manages Team A)
    - member_a (member of Team A)
    - manager_b (creates and manages Team B)
    - normal_user (belongs to no team)
    - project_a in Team A
    - task_a in Project A
    """
    admin_token = register_and_login(client, "audit_admin@example.com")
    make_admin(db_session, "audit_admin@example.com")

    mgr_a_token = register_and_login(client, "audit_mgr_a@example.com")
    mem_a_token = register_and_login(client, "audit_mem_a@example.com")
    mgr_b_token = register_and_login(client, "audit_mgr_b@example.com")
    normal_token = register_and_login(client, "audit_normal@example.com")

    # Manager A creates Team A
    team_a = client.post("/teams", headers=auth(mgr_a_token), json={"name": "Team Alpha"}).json()
    team_a_id = team_a["id"]

    # Manager A adds Member A
    client.post(f"/teams/{team_a_id}/members", headers=auth(mgr_a_token),
                json={"email": "audit_mem_a@example.com", "role": "MEMBER"})

    # Manager A creates Project A
    proj_a = client.post(f"/teams/{team_a_id}/projects", headers=auth(mgr_a_token),
                         json={"name": "Project Alpha"}).json()
    proj_a_id = proj_a["id"]

    # Manager B creates Team B
    team_b = client.post("/teams", headers=auth(mgr_b_token), json={"name": "Team Beta"}).json()
    team_b_id = team_b["id"]

    return {
        "admin_token": admin_token,
        "mgr_a_token": mgr_a_token,
        "mem_a_token": mem_a_token,
        "mgr_b_token": mgr_b_token,
        "normal_token": normal_token,
        "team_a_id": team_a_id,
        "team_b_id": team_b_id,
        "proj_a_id": proj_a_id,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. AUDIT LOG CREATION (17 ACTIONS)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogCreation:

    def test_user_registered(self, client, db_session):
        register_and_login(client, "audit_reg@example.com")
        user = db_session.query(User).filter(User.email == "audit_reg@example.com").first()

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.USER_REGISTERED,
            AuditLog.entity_id == user.id,
        ).first()

        assert log is not None
        assert log.actor_id == user.id
        assert log.entity_type == "user"
        assert log.team_id is None
        assert log.metadata_["email"] == "audit_reg@example.com"

    def test_user_updated(self, client, db_session):
        token = register_and_login(client, "audit_upd@example.com")
        user = db_session.query(User).filter(User.email == "audit_upd@example.com").first()

        client.patch("/users/me", headers=auth(token), json={"name": "Updated Name"})

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.USER_UPDATED,
            AuditLog.entity_id == user.id,
        ).first()

        assert log is not None
        assert log.actor_id == user.id
        assert log.entity_type == "user"
        assert log.metadata_["name"] == "Updated Name"

    def test_user_deactivated(self, client, db_session):
        token = register_and_login(client, "audit_deact@example.com")
        user = db_session.query(User).filter(User.email == "audit_deact@example.com").first()

        res = client.post("/users/me/deactivate", headers=auth(token))
        assert res.status_code == 200

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.USER_DEACTIVATED,
            AuditLog.entity_id == user.id,
        ).first()

        assert log is not None
        assert log.actor_id == user.id
        assert log.entity_type == "user"

    def test_team_created(self, client, db_session):
        token = register_and_login(client, "team_creator@example.com")
        res = client.post("/teams", headers=auth(token), json={"name": "New Audit Team"})
        team_id = UUID(res.json()["id"])
        user_id = UUID(me(client, token)["id"])

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TEAM_CREATED,
            AuditLog.entity_id == team_id,
        ).first()

        assert log is not None
        assert log.actor_id == user_id
        assert log.entity_type == "team"
        assert log.team_id == team_id

    def test_member_added(self, client, db_session, audit_setup):
        mgr = audit_setup["mgr_a_token"]
        team_id = UUID(audit_setup["team_a_id"])
        new_user_token = register_and_login(client, "new_member@example.com")
        new_user_id = UUID(me(client, new_user_token)["id"])

        client.post(f"/teams/{team_id}/members", headers=auth(mgr),
                    json={"email": "new_member@example.com", "role": "MEMBER"})

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.MEMBER_ADDED,
            AuditLog.team_id == team_id,
        ).order_by(AuditLog.created_at.desc()).first()

        assert log is not None
        assert log.metadata_["user_id"] == str(new_user_id)
        assert log.metadata_["role"] == "MEMBER"

    def test_member_role_changed(self, client, db_session, audit_setup):
        mgr = audit_setup["mgr_a_token"]
        team_id = UUID(audit_setup["team_a_id"])
        mem_id = UUID(me(client, audit_setup["mem_a_token"])["id"])

        client.patch(f"/teams/{team_id}/members/{mem_id}", headers=auth(mgr),
                     json={"role": "MANAGER"})

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.MEMBER_ROLE_CHANGED,
            AuditLog.team_id == team_id,
        ).first()

        assert log is not None
        assert log.metadata_["old_role"] == "MEMBER"
        assert log.metadata_["new_role"] == "MANAGER"

    def test_member_removed(self, client, db_session, audit_setup):
        mgr = audit_setup["mgr_a_token"]
        team_id = UUID(audit_setup["team_a_id"])
        mem_id = UUID(me(client, audit_setup["mem_a_token"])["id"])

        client.delete(f"/teams/{team_id}/members/{mem_id}", headers=auth(mgr))

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.MEMBER_REMOVED,
            AuditLog.team_id == team_id,
        ).first()

        assert log is not None
        assert log.metadata_["user_id"] == str(mem_id)

    def test_project_created(self, client, db_session, audit_setup):
        proj_id = UUID(audit_setup["proj_a_id"])
        team_id = UUID(audit_setup["team_a_id"])

        log = db_session.query(AuditLog).filter(
            AuditAction.PROJECT_CREATED == AuditLog.action,
            AuditLog.entity_id == proj_id,
        ).first()

        assert log is not None
        assert log.team_id == team_id
        assert log.entity_type == "project"

    def test_project_updated(self, client, db_session, audit_setup):
        mgr = audit_setup["mgr_a_token"]
        proj_id = UUID(audit_setup["proj_a_id"])

        client.patch(f"/projects/{proj_id}", headers=auth(mgr), json={"name": "Renamed Alpha"})

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.PROJECT_UPDATED,
            AuditLog.entity_id == proj_id,
        ).first()

        assert log is not None
        assert log.metadata_["name"] == "Renamed Alpha"

    def test_project_deleted(self, client, db_session, audit_setup):
        mgr = audit_setup["mgr_a_token"]
        proj_id = UUID(audit_setup["proj_a_id"])
        team_id = UUID(audit_setup["team_a_id"])

        client.delete(f"/projects/{proj_id}?confirm=true", headers=auth(mgr))

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.PROJECT_DELETED,
            AuditLog.entity_id == proj_id,
        ).first()

        assert log is not None
        assert log.team_id == team_id

    def test_personal_task_created(self, client, db_session):
        token = register_and_login(client, "pt_audit@example.com")
        res = client.post("/tasks", headers=auth(token), json={"title": "Personal Task"})
        task_id = UUID(res.json()["id"])

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TASK_CREATED,
            AuditLog.entity_id == task_id,
        ).first()

        assert log is not None
        assert log.team_id is None
        assert log.metadata_["title"] == "Personal Task"

    def test_project_task_created(self, client, db_session, audit_setup):
        mgr = audit_setup["mgr_a_token"]
        proj_id = UUID(audit_setup["proj_a_id"])
        team_id = UUID(audit_setup["team_a_id"])

        res = client.post(f"/projects/{proj_id}/tasks", headers=auth(mgr), json={"title": "Team Task"})
        task_id = UUID(res.json()["id"])

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TASK_CREATED,
            AuditLog.entity_id == task_id,
        ).first()

        assert log is not None
        assert log.team_id == team_id

    def test_task_updated(self, client, db_session):
        token = register_and_login(client, "task_upd@example.com")
        res = client.post("/tasks", headers=auth(token), json={"title": "Initial Title"})
        task_id = UUID(res.json()["id"])

        client.patch(f"/tasks/{task_id}", headers=auth(token), json={"title": "New Title"})

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TASK_UPDATED,
            AuditLog.entity_id == task_id,
        ).first()

        assert log is not None
        assert log.metadata_["title"] == "New Title"

    def test_task_completed(self, client, db_session):
        token = register_and_login(client, "task_done@example.com")
        res = client.post("/tasks", headers=auth(token), json={"title": "Do Dishes"})
        task_id = UUID(res.json()["id"])

        client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "COMPLETED"})

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TASK_COMPLETED,
            AuditLog.entity_id == task_id,
        ).first()

        assert log is not None
        assert log.metadata_["new_status"] == "COMPLETED"

    def test_task_reopened(self, client, db_session):
        token = register_and_login(client, "task_reopen@example.com")
        res = client.post("/tasks", headers=auth(token), json={"title": "Reopen Me"})
        task_id = UUID(res.json()["id"])

        client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "COMPLETED"})
        client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "TODO"})

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TASK_REOPENED,
            AuditLog.entity_id == task_id,
        ).first()

        assert log is not None
        assert log.metadata_["new_status"] == "TODO"

    def test_task_assigned_and_unassigned(self, client, db_session, audit_setup):
        mgr = audit_setup["mgr_a_token"]
        proj_id = UUID(audit_setup["proj_a_id"])
        mem_id = UUID(me(client, audit_setup["mem_a_token"])["id"])

        res = client.post(f"/projects/{proj_id}/tasks", headers=auth(mgr), json={"title": "Assign Me"})
        task_id = UUID(res.json()["id"])

        # Assign
        client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr), json={"assigned_to": str(mem_id)})
        assign_log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TASK_ASSIGNED,
            AuditLog.entity_id == task_id,
        ).first()
        assert assign_log is not None
        assert assign_log.metadata_["assigned_to"] == str(mem_id)

        # Unassign
        client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr), json={"assigned_to": None})
        unassign_log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TASK_UNASSIGNED,
            AuditLog.entity_id == task_id,
        ).first()
        assert unassign_log is not None

    def test_task_deleted(self, client, db_session):
        token = register_and_login(client, "task_del@example.com")
        res = client.post("/tasks", headers=auth(token), json={"title": "Delete Me"})
        task_id = UUID(res.json()["id"])

        client.delete(f"/tasks/{task_id}", headers=auth(token))

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.TASK_DELETED,
            AuditLog.entity_id == task_id,
        ).first()

        assert log is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ACTOR SECURITY & SENSITIVE DATA
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditSecurity:

    def test_actor_comes_from_authenticated_user(self, client, db_session):
        token = register_and_login(client, "actor_sec@example.com")
        user_id = UUID(me(client, token)["id"])

        res = client.post("/tasks", headers=auth(token), json={"title": "Actor Test"})
        task_id = UUID(res.json()["id"])

        log = db_session.query(AuditLog).filter(AuditLog.entity_id == task_id).first()
        assert log.actor_id == user_id

    def test_sensitive_data_not_logged_on_register(self, client, db_session):
        register_and_login(client, "secret_user@example.com", password="SuperSecretPassword123!")
        user = db_session.query(User).filter(User.email == "secret_user@example.com").first()

        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.USER_REGISTERED,
            AuditLog.entity_id == user.id,
        ).first()

        assert "SuperSecretPassword123!" not in str(log.description)
        assert "SuperSecretPassword123!" not in str(log.metadata_)
        assert "password_hash" not in log.metadata_

    def test_sensitive_data_not_logged_on_update(self, client, db_session):
        token = register_and_login(client, "sec_upd@example.com")
        client.patch("/users/me", headers=auth(token), json={"name": "Safe Name"})

        user = db_session.query(User).filter(User.email == "sec_upd@example.com").first()
        log = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.USER_UPDATED,
            AuditLog.entity_id == user.id,
        ).first()

        assert "password" not in str(log.metadata_)
        assert "password_hash" not in str(log.metadata_)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. TRANSACTION CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════════

class TestTransactionConsistency:

    def test_failed_team_member_addition_leaves_no_audit(self, client, db_session, audit_setup):
        mgr = audit_setup["mgr_a_token"]
        team_id = audit_setup["team_a_id"]

        initial_count = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.MEMBER_ADDED,
            AuditLog.team_id == UUID(team_id),
        ).count()

        # Attempt to add user that does not exist -> 404
        res = client.post(f"/teams/{team_id}/members", headers=auth(mgr),
                          json={"email": "ghost_user_999@example.com", "role": "MEMBER"})
        assert res.status_code == 404

        after_count = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.MEMBER_ADDED,
            AuditLog.team_id == UUID(team_id),
        ).count()

        assert after_count == initial_count

    def test_duplicate_team_member_leaves_no_audit(self, client, db_session, audit_setup):
        mgr = audit_setup["mgr_a_token"]
        team_id = audit_setup["team_a_id"]

        initial_count = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.MEMBER_ADDED,
            AuditLog.team_id == UUID(team_id),
        ).count()

        # Attempt to add member who is already in team -> 409
        res = client.post(f"/teams/{team_id}/members", headers=auth(mgr),
                          json={"email": "audit_mem_a@example.com", "role": "MEMBER"})
        assert res.status_code == 409

        after_count = db_session.query(AuditLog).filter(
            AuditLog.action == AuditAction.MEMBER_ADDED,
            AuditLog.team_id == UUID(team_id),
        ).count()

        assert after_count == initial_count


# ═══════════════════════════════════════════════════════════════════════════════
# 4. AUTHORIZATION & RBAC
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditAuthorization:

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/audit-logs")
        assert res.status_code == 401

    def test_normal_user_returns_403(self, client, audit_setup):
        res = client.get("/audit-logs", headers=auth(audit_setup["normal_token"]))
        assert res.status_code == 403

    def test_team_member_returns_403(self, client, audit_setup):
        res = client.get("/audit-logs", headers=auth(audit_setup["mem_a_token"]))
        assert res.status_code == 403

    def test_admin_can_access_all_logs(self, client, audit_setup):
        res = client.get("/audit-logs", headers=auth(audit_setup["admin_token"]))
        assert res.status_code == 200
        d = res.json()
        assert "items" in d
        assert d["total"] >= 1

    def test_team_manager_can_access_team_logs(self, client, audit_setup):
        res = client.get("/audit-logs", headers=auth(audit_setup["mgr_a_token"]))
        assert res.status_code == 200
        d = res.json()
        assert d["total"] >= 1
        # Manager A should only see logs for Team A
        for item in d["items"]:
            assert item["team_id"] == audit_setup["team_a_id"]

    def test_team_manager_cannot_see_unrelated_team_logs(self, client, audit_setup):
        # Manager B should only see Team B logs
        res = client.get("/audit-logs", headers=auth(audit_setup["mgr_b_token"]))
        assert res.status_code == 200
        d = res.json()
        for item in d["items"]:
            assert item["team_id"] == audit_setup["team_b_id"]

    def test_team_manager_cannot_see_user_level_events(self, client, audit_setup):
        # User level events have team_id = None, which manager cannot see
        res = client.get("/audit-logs", headers=auth(audit_setup["mgr_a_token"]))
        d = res.json()
        for item in d["items"]:
            assert item["team_id"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FILTERING
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditFiltering:

    def test_filter_by_action(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        res = client.get("/audit-logs?action=TEAM_CREATED", headers=auth(admin))
        assert res.status_code == 200
        d = res.json()
        assert d["total"] >= 1
        assert all(item["action"] == "TEAM_CREATED" for item in d["items"])

    def test_filter_by_entity_type(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        res = client.get("/audit-logs?entity_type=project", headers=auth(admin))
        assert res.status_code == 200
        d = res.json()
        assert d["total"] >= 1
        assert all(item["entity_type"] == "project" for item in d["items"])

    def test_filter_by_actor_id(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        mgr_a_id = me(client, audit_setup["mgr_a_token"])["id"]

        res = client.get(f"/audit-logs?actor_id={mgr_a_id}", headers=auth(admin))
        assert res.status_code == 200
        d = res.json()
        assert d["total"] >= 1
        assert all(item["actor_id"] == mgr_a_id for item in d["items"])

    def test_filter_by_entity_id(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        proj_id = audit_setup["proj_a_id"]

        res = client.get(f"/audit-logs?entity_id={proj_id}", headers=auth(admin))
        assert res.status_code == 200
        d = res.json()
        assert d["total"] >= 1
        assert all(item["entity_id"] == proj_id for item in d["items"])

    def test_filter_by_date_range(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        now = datetime.utcnow()
        past = iso(now - timedelta(days=1))
        future = iso(now + timedelta(days=1))

        res = client.get(f"/audit-logs?date_from={past}&date_to={future}", headers=auth(admin))
        assert res.status_code == 200
        d = res.json()
        assert d["total"] >= 1

    def test_combined_filters(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        mgr_a_id = me(client, audit_setup["mgr_a_token"])["id"]

        res = client.get(
            f"/audit-logs?action=PROJECT_CREATED&entity_type=project&actor_id={mgr_a_id}",
            headers=auth(admin),
        )
        assert res.status_code == 200
        d = res.json()
        assert d["total"] == 1
        assert d["items"][0]["entity_id"] == audit_setup["proj_a_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PAGINATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditPagination:

    def test_default_pagination(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        res = client.get("/audit-logs", headers=auth(admin))
        assert res.status_code == 200
        d = res.json()
        assert d["page"] == 1
        assert d["page_size"] == 20
        assert "items" in d
        assert "total" in d
        assert "total_pages" in d

    def test_custom_page_and_page_size(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        res = client.get("/audit-logs?page=1&page_size=2", headers=auth(admin))
        assert res.status_code == 200
        d = res.json()
        assert d["page"] == 1
        assert d["page_size"] == 2
        assert len(d["items"]) == 2

    def test_invalid_page_returns_422(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        res = client.get("/audit-logs?page=0", headers=auth(admin))
        assert res.status_code == 422

    def test_invalid_page_size_returns_422(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        res = client.get("/audit-logs?page_size=0", headers=auth(admin))
        assert res.status_code == 422

    def test_page_size_max_boundary(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        assert client.get("/audit-logs?page_size=100", headers=auth(admin)).status_code == 200
        assert client.get("/audit-logs?page_size=101", headers=auth(admin)).status_code == 422

    def test_total_reflects_only_authorized_logs(self, client, audit_setup):
        admin = audit_setup["admin_token"]
        mgr_a = audit_setup["mgr_a_token"]

        total_admin = client.get("/audit-logs", headers=auth(admin)).json()["total"]
        total_mgr_a = client.get("/audit-logs", headers=auth(mgr_a)).json()["total"]

        # Admin sees all logs, manager only sees Team A logs
        assert total_admin > total_mgr_a
        assert total_mgr_a >= 1
