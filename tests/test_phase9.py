"""
Phase 9 — API Quality & Error Handling tests.

Covers:
- Empty / blank string inputs returning 422 (title, name)
- Deactivate user endpoint
- 401 for unauthenticated requests (spot-check)
- No password_hash in any user response (additional paths)
"""
import pytest
from app.models.user import User
from app.models.enums import GlobalRole


# ─── Helpers ─────────────────────────────────────────────────────────────────

def register_and_login(client, email, name=None, password="pass"):
    name = name or email.split("@")[0]
    client.post("/auth/register", json={"name": name, "email": email, "password": password})
    res = client.post("/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── Input Validation: empty / blank title ───────────────────────────────────

class TestEmptyTitleValidation:
    def test_create_personal_task_empty_title_returns_422(self, client):
        token = register_and_login(client, "p9_task1@example.com")
        res = client.post("/tasks", headers=auth(token), json={"title": ""})
        assert res.status_code == 422

    def test_create_personal_task_missing_title_returns_422(self, client):
        token = register_and_login(client, "p9_task2@example.com")
        res = client.post("/tasks", headers=auth(token), json={"description": "no title"})
        assert res.status_code == 422

    def test_create_project_task_empty_title_returns_422(self, client):
        mgr = register_and_login(client, "p9_ptask_mgr@example.com")
        team = client.post("/teams", headers=auth(mgr), json={"name": "P9 Team"}).json()
        project = client.post(
            f"/teams/{team['id']}/projects",
            headers=auth(mgr),
            json={"name": "P9 Project"},
        ).json()
        res = client.post(
            f"/projects/{project['id']}/tasks",
            headers=auth(mgr),
            json={"title": ""},
        )
        assert res.status_code == 422

    def test_update_task_empty_title_returns_422(self, client):
        token = register_and_login(client, "p9_upd_task@example.com")
        task = client.post("/tasks", headers=auth(token), json={"title": "Original"}).json()
        res = client.patch(f"/tasks/{task['id']}", headers=auth(token), json={"title": ""})
        assert res.status_code == 422

    def test_create_personal_task_valid_title_succeeds(self, client):
        token = register_and_login(client, "p9_task_ok@example.com")
        res = client.post("/tasks", headers=auth(token), json={"title": "Valid Title"})
        assert res.status_code == 201
        assert res.json()["title"] == "Valid Title"


# ─── Input Validation: empty / blank team name ───────────────────────────────

class TestEmptyTeamNameValidation:
    def test_create_team_empty_name_returns_422(self, client):
        token = register_and_login(client, "p9_team1@example.com")
        res = client.post("/teams", headers=auth(token), json={"name": ""})
        assert res.status_code == 422

    def test_create_team_missing_name_returns_422(self, client):
        token = register_and_login(client, "p9_team2@example.com")
        res = client.post("/teams", headers=auth(token), json={"description": "no name"})
        assert res.status_code == 422

    def test_create_team_valid_name_succeeds(self, client):
        token = register_and_login(client, "p9_team_ok@example.com")
        res = client.post("/teams", headers=auth(token), json={"name": "Valid Team"})
        assert res.status_code == 201
        assert res.json()["name"] == "Valid Team"


# ─── Input Validation: empty / blank project name ────────────────────────────

class TestEmptyProjectNameValidation:
    def test_create_project_empty_name_returns_422(self, client):
        mgr = register_and_login(client, "p9_proj1@example.com")
        team = client.post("/teams", headers=auth(mgr), json={"name": "P9 Proj Team"}).json()
        res = client.post(
            f"/teams/{team['id']}/projects",
            headers=auth(mgr),
            json={"name": ""},
        )
        assert res.status_code == 422

    def test_update_project_empty_name_returns_422(self, client):
        mgr = register_and_login(client, "p9_proj2@example.com")
        team = client.post("/teams", headers=auth(mgr), json={"name": "P9 Proj Team 2"}).json()
        project = client.post(
            f"/teams/{team['id']}/projects",
            headers=auth(mgr),
            json={"name": "Good Name"},
        ).json()
        res = client.patch(
            f"/projects/{project['id']}",
            headers=auth(mgr),
            json={"name": ""},
        )
        assert res.status_code == 422

    def test_create_project_valid_name_succeeds(self, client):
        mgr = register_and_login(client, "p9_proj_ok@example.com")
        team = client.post("/teams", headers=auth(mgr), json={"name": "P9 OK Team"}).json()
        res = client.post(
            f"/teams/{team['id']}/projects",
            headers=auth(mgr),
            json={"name": "Valid Project"},
        )
        assert res.status_code == 201
        assert res.json()["name"] == "Valid Project"


# ─── Deactivate user endpoint ─────────────────────────────────────────────────

class TestDeactivateUser:
    def test_deactivate_self_returns_200_with_is_active_false(self, client):
        token = register_and_login(client, "p9_deact1@example.com")
        res = client.post("/users/me/deactivate", headers=auth(token))
        assert res.status_code == 200
        data = res.json()
        assert data["is_active"] is False
        assert "password_hash" not in data
        assert "password" not in data

    def test_deactivate_unauthenticated_returns_401(self, client):
        res = client.post("/users/me/deactivate")
        assert res.status_code == 401

    def test_deactivated_user_cannot_login(self, client):
        token = register_and_login(client, "p9_deact2@example.com")
        client.post("/users/me/deactivate", headers=auth(token))
        # After deactivation, login should still succeed (credentials valid)
        # but accessing /users/me with a new token should fail
        login_res = client.post(
            "/auth/login",
            json={"email": "p9_deact2@example.com", "password": "pass"},
        )
        # The login endpoint checks is_active and returns 403
        assert login_res.status_code == 403


# ─── Authorization: 401 spot-checks ──────────────────────────────────────────

class TestUnauthenticated401:
    def test_get_tasks_unauthenticated(self, client):
        res = client.get("/tasks")
        assert res.status_code == 401

    def test_get_teams_unauthenticated(self, client):
        res = client.get("/teams")
        assert res.status_code == 401

    def test_get_users_me_unauthenticated(self, client):
        res = client.get("/users/me")
        assert res.status_code == 401

    def test_get_audit_logs_unauthenticated(self, client):
        res = client.get("/audit-logs")
        assert res.status_code == 401


# ─── Sensitive data: no password_hash in any user response ───────────────────

class TestNoPasswordInResponses:
    def test_register_no_password_hash(self, client):
        res = client.post(
            "/auth/register",
            json={"name": "P9 Pw1", "email": "p9_pw1@example.com", "password": "secret"},
        )
        assert res.status_code == 201
        assert "password_hash" not in res.json()
        assert "password" not in res.json()

    def test_auth_me_no_password_hash(self, client):
        token = register_and_login(client, "p9_pw2@example.com")
        res = client.get("/auth/me", headers=auth(token))
        assert res.status_code == 200
        assert "password_hash" not in res.json()

    def test_users_me_no_password_hash(self, client):
        token = register_and_login(client, "p9_pw3@example.com")
        res = client.get("/users/me", headers=auth(token))
        assert res.status_code == 200
        assert "password_hash" not in res.json()

    def test_patch_users_me_no_password_hash(self, client):
        token = register_and_login(client, "p9_pw4@example.com")
        res = client.patch("/users/me", headers=auth(token), json={"name": "Updated"})
        assert res.status_code == 200
        assert "password_hash" not in res.json()
