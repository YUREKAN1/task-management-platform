"""
Phase 6 – Task Management Tests
Tests for personal tasks and project tasks including auth, authorization,
status lifecycle, assignment rules, and security.
"""
import pytest
from uuid import uuid4


# ─── Helpers ─────────────────────────────────────────────────────────────────

def register_and_login(client, email, password="pass"):
    client.post("/auth/register", json={"name": email.split("@")[0], "email": email, "password": password})
    return client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def me(client, token):
    return client.get("/users/me", headers=auth(token)).json()


@pytest.fixture
def team_setup(client):
    """Manager + member + outsider, one team, one project inside it."""
    manager_token = register_and_login(client, "task_mgr@example.com")
    member_token  = register_and_login(client, "task_mem@example.com")
    outsider_token = register_and_login(client, "task_out@example.com")
    other_team_member_token = register_and_login(client, "task_other@example.com")

    team = client.post("/teams", headers=auth(manager_token), json={"name": "Task Team"}).json()
    team_id = team["id"]

    client.post(f"/teams/{team_id}/members", headers=auth(manager_token),
                json={"email": "task_mem@example.com", "role": "MEMBER"})

    project = client.post(f"/teams/{team_id}/projects", headers=auth(manager_token),
                          json={"name": "Task Project"}).json()
    project_id = project["id"]

    # other_team_member belongs to a completely different team
    other_team = client.post("/teams", headers=auth(other_team_member_token),
                              json={"name": "Other Team"}).json()

    return {
        "manager_token":          manager_token,
        "member_token":           member_token,
        "outsider_token":         outsider_token,
        "other_team_member_token": other_team_member_token,
        "team_id":                team_id,
        "project_id":             project_id,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PERSONAL TASK TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersonalTaskCreate:
    def test_create_success(self, client):
        token = register_and_login(client, "pt_create@example.com")
        res = client.post("/tasks", headers=auth(token),
                          json={"title": "My task", "priority": "HIGH"})
        assert res.status_code == 201
        d = res.json()
        assert d["title"] == "My task"
        assert d["priority"] == "HIGH"
        assert d["project_id"] is None
        assert d["status"] == "TODO"

    def test_unauthenticated_rejected(self, client):
        res = client.post("/tasks", json={"title": "No auth"})
        assert res.status_code == 401

    def test_created_by_from_auth(self, client):
        token = register_and_login(client, "pt_cby@example.com")
        user_id = me(client, token)["id"]
        res = client.post("/tasks", headers=auth(token),
                          json={"title": "owner", "created_by": str(uuid4())})
        assert res.status_code == 201
        assert res.json()["created_by"] == user_id   # spoofed value ignored

    def test_project_id_is_null(self, client):
        token = register_and_login(client, "pt_null@example.com")
        res = client.post("/tasks", headers=auth(token), json={"title": "personal"})
        assert res.json()["project_id"] is None

    def test_default_priority_and_status(self, client):
        token = register_and_login(client, "pt_defaults@example.com")
        res = client.post("/tasks", headers=auth(token), json={"title": "defaults"})
        d = res.json()
        assert d["priority"] == "MEDIUM"
        assert d["status"] == "TODO"
        assert d["completed_at"] is None

    def test_invalid_priority_rejected(self, client):
        token = register_and_login(client, "pt_inv_prio@example.com")
        res = client.post("/tasks", headers=auth(token),
                          json={"title": "bad", "priority": "URGENT"})
        assert res.status_code == 422


class TestPersonalTaskList:
    def test_creator_sees_own_tasks(self, client):
        token = register_and_login(client, "ptl_own@example.com")
        client.post("/tasks", headers=auth(token), json={"title": "T1"})
        client.post("/tasks", headers=auth(token), json={"title": "T2"})
        res = client.get("/tasks", headers=auth(token))
        assert res.status_code == 200
        assert len(res.json()["items"]) == 2

    def test_other_user_sees_no_tasks(self, client):
        t1 = register_and_login(client, "ptl_a@example.com")
        t2 = register_and_login(client, "ptl_b@example.com")
        client.post("/tasks", headers=auth(t1), json={"title": "Private"})
        res = client.get("/tasks", headers=auth(t2))
        assert res.status_code == 200
        assert res.json()["items"] == []

    def test_project_tasks_not_in_personal_list(self, client, team_setup):
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        # create project task
        client.post(f"/projects/{pid}/tasks", headers=auth(mgr), json={"title": "proj task"})
        # personal list for manager must not include project task
        res = client.get("/tasks", headers=auth(mgr))
        assert all(t["project_id"] is None for t in res.json()["items"])


class TestPersonalTaskGet:
    def test_creator_can_get(self, client):
        token = register_and_login(client, "ptg_creator@example.com")
        task_id = client.post("/tasks", headers=auth(token), json={"title": "mine"}).json()["id"]
        res = client.get(f"/tasks/{task_id}", headers=auth(token))
        assert res.status_code == 200

    def test_other_user_gets_403(self, client):
        t1 = register_and_login(client, "ptg_own@example.com")
        t2 = register_and_login(client, "ptg_other@example.com")
        task_id = client.post("/tasks", headers=auth(t1), json={"title": "mine"}).json()["id"]
        assert client.get(f"/tasks/{task_id}", headers=auth(t2)).status_code == 403

    def test_nonexistent_returns_404(self, client):
        token = register_and_login(client, "ptg_404@example.com")
        assert client.get(f"/tasks/{uuid4()}", headers=auth(token)).status_code == 404


class TestPersonalTaskUpdate:
    def test_creator_can_update(self, client):
        token = register_and_login(client, "ptu_own@example.com")
        task_id = client.post("/tasks", headers=auth(token), json={"title": "orig"}).json()["id"]
        res = client.patch(f"/tasks/{task_id}", headers=auth(token), json={"title": "updated"})
        assert res.status_code == 200
        assert res.json()["title"] == "updated"

    def test_other_user_cannot_update(self, client):
        t1 = register_and_login(client, "ptu_a@example.com")
        t2 = register_and_login(client, "ptu_b@example.com")
        task_id = client.post("/tasks", headers=auth(t1), json={"title": "mine"}).json()["id"]
        assert client.patch(f"/tasks/{task_id}", headers=auth(t2), json={"title": "hacked"}).status_code == 403

    def test_protected_fields_cannot_be_changed(self, client):
        token = register_and_login(client, "ptu_prot@example.com")
        orig = client.post("/tasks", headers=auth(token), json={"title": "t"}).json()
        task_id = orig["id"]
        res = client.patch(f"/tasks/{task_id}", headers=auth(token),
                           json={"title": "ok", "created_by": str(uuid4()),
                                 "project_id": str(uuid4()), "completed_at": "2025-01-01T00:00:00Z"})
        assert res.status_code == 200
        d = res.json()
        assert d["created_by"] == orig["created_by"]
        assert d["project_id"] is None


class TestPersonalTaskDelete:
    def test_creator_can_delete(self, client):
        token = register_and_login(client, "ptd_own@example.com")
        task_id = client.post("/tasks", headers=auth(token), json={"title": "bye"}).json()["id"]
        assert client.delete(f"/tasks/{task_id}", headers=auth(token)).status_code == 204
        assert client.get(f"/tasks/{task_id}", headers=auth(token)).status_code == 404

    def test_other_user_cannot_delete(self, client):
        t1 = register_and_login(client, "ptd_a@example.com")
        t2 = register_and_login(client, "ptd_b@example.com")
        task_id = client.post("/tasks", headers=auth(t1), json={"title": "mine"}).json()["id"]
        assert client.delete(f"/tasks/{task_id}", headers=auth(t2)).status_code == 403

    def test_nonexistent_returns_404(self, client):
        token = register_and_login(client, "ptd_404@example.com")
        assert client.delete(f"/tasks/{uuid4()}", headers=auth(token)).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS & completed_at LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskStatusLifecycle:
    def _make_task(self, client, token):
        return client.post("/tasks", headers=auth(token), json={"title": "lifecycle"}).json()["id"]

    def test_todo_to_in_progress(self, client):
        token = register_and_login(client, "sl_tip@example.com")
        task_id = self._make_task(client, token)
        res = client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "IN_PROGRESS"})
        assert res.status_code == 200
        d = res.json()
        assert d["status"] == "IN_PROGRESS"
        assert d["completed_at"] is None

    def test_in_progress_to_completed(self, client):
        token = register_and_login(client, "sl_ipc@example.com")
        task_id = self._make_task(client, token)
        client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "IN_PROGRESS"})
        res = client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "COMPLETED"})
        assert res.status_code == 200
        d = res.json()
        assert d["status"] == "COMPLETED"
        assert d["completed_at"] is not None

    def test_completed_to_todo_clears_completed_at(self, client):
        token = register_and_login(client, "sl_ct@example.com")
        task_id = self._make_task(client, token)
        client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "COMPLETED"})
        res = client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "TODO"})
        assert res.status_code == 200
        assert res.json()["completed_at"] is None

    def test_completed_to_in_progress_clears_completed_at(self, client):
        token = register_and_login(client, "sl_cip@example.com")
        task_id = self._make_task(client, token)
        client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "COMPLETED"})
        res = client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "IN_PROGRESS"})
        assert res.status_code == 200
        assert res.json()["completed_at"] is None

    def test_client_cannot_control_completed_at(self, client):
        token = register_and_login(client, "sl_spoofca@example.com")
        task_id = self._make_task(client, token)
        # Send completed_at in body for a TODO task – must be ignored
        res = client.patch(f"/tasks/{task_id}", headers=auth(token),
                           json={"completed_at": "2020-01-01T00:00:00Z"})
        assert res.status_code == 200
        assert res.json()["completed_at"] is None  # backend controls this

    def test_invalid_status_rejected(self, client):
        token = register_and_login(client, "sl_inv@example.com")
        task_id = self._make_task(client, token)
        res = client.patch(f"/tasks/{task_id}", headers=auth(token), json={"status": "DONE"})
        assert res.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TASK TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectTaskCreate:
    def test_manager_can_create(self, client, team_setup):
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        res = client.post(f"/projects/{pid}/tasks", headers=auth(mgr),
                          json={"title": "Sprint 1 task"})
        assert res.status_code == 201
        d = res.json()
        assert d["project_id"] == pid
        assert d["title"] == "Sprint 1 task"

    def test_member_cannot_create(self, client, team_setup):
        mem = team_setup["member_token"]
        pid = team_setup["project_id"]
        res = client.post(f"/projects/{pid}/tasks", headers=auth(mem),
                          json={"title": "should fail"})
        assert res.status_code == 403

    def test_outsider_cannot_create(self, client, team_setup):
        out = team_setup["outsider_token"]
        pid = team_setup["project_id"]
        res = client.post(f"/projects/{pid}/tasks", headers=auth(out),
                          json={"title": "should fail"})
        assert res.status_code == 403

    def test_nonexistent_project_404(self, client, team_setup):
        mgr = team_setup["manager_token"]
        res = client.post(f"/projects/{uuid4()}/tasks", headers=auth(mgr),
                          json={"title": "ghost"})
        assert res.status_code == 404

    def test_unauthenticated_rejected(self, client, team_setup):
        pid = team_setup["project_id"]
        res = client.post(f"/projects/{pid}/tasks", json={"title": "no auth"})
        assert res.status_code == 401

    def test_created_by_from_auth(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mgr_id = me(client, mgr)["id"]
        pid = team_setup["project_id"]
        res = client.post(f"/projects/{pid}/tasks", headers=auth(mgr),
                          json={"title": "t", "created_by": str(uuid4())})
        assert res.status_code == 201
        assert res.json()["created_by"] == mgr_id

    def test_project_id_from_url(self, client, team_setup):
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        res = client.post(f"/projects/{pid}/tasks", headers=auth(mgr),
                          json={"title": "t", "project_id": str(uuid4())})
        assert res.status_code == 201
        assert res.json()["project_id"] == pid

    def test_assign_to_team_member_accepted(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem_id = me(client, team_setup["member_token"])["id"]
        pid = team_setup["project_id"]
        res = client.post(f"/projects/{pid}/tasks", headers=auth(mgr),
                          json={"title": "assigned", "assigned_to": str(mem_id)})
        assert res.status_code == 201
        assert res.json()["assigned_to"] == str(mem_id)

    def test_assign_to_outsider_rejected(self, client, team_setup):
        mgr = team_setup["manager_token"]
        out_id = me(client, team_setup["outsider_token"])["id"]
        pid = team_setup["project_id"]
        res = client.post(f"/projects/{pid}/tasks", headers=auth(mgr),
                          json={"title": "cross-team", "assigned_to": str(out_id)})
        assert res.status_code == 400

    def test_assign_to_nonexistent_user_rejected(self, client, team_setup):
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        res = client.post(f"/projects/{pid}/tasks", headers=auth(mgr),
                          json={"title": "ghost assign", "assigned_to": str(uuid4())})
        assert res.status_code == 404

    def test_assign_to_inactive_user_rejected(self, client, team_setup, db_session):
        from app.models.user import User
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        # Register a user and add to team
        inactive_token = register_and_login(client, "task_inactive@example.com")
        inactive_id = me(client, inactive_token)["id"]
        team_id = team_setup["team_id"]
        client.post(f"/teams/{team_id}/members", headers=auth(mgr),
                    json={"email": "task_inactive@example.com", "role": "MEMBER"})
        # Deactivate
        u = db_session.query(User).filter(User.email == "task_inactive@example.com").first()
        u.is_active = False
        db_session.commit()
        res = client.post(f"/projects/{pid}/tasks", headers=auth(mgr),
                          json={"title": "inactive assign", "assigned_to": str(inactive_id)})
        assert res.status_code == 400


class TestProjectTaskList:
    def test_member_can_list(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem = team_setup["member_token"]
        pid = team_setup["project_id"]
        client.post(f"/projects/{pid}/tasks", headers=auth(mgr), json={"title": "T"})
        res = client.get(f"/projects/{pid}/tasks", headers=auth(mem))
        assert res.status_code == 200
        assert len(res.json()["items"]) >= 1

    def test_manager_can_list(self, client, team_setup):
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        client.post(f"/projects/{pid}/tasks", headers=auth(mgr), json={"title": "T"})
        res = client.get(f"/projects/{pid}/tasks", headers=auth(mgr))
        assert res.status_code == 200

    def test_outsider_cannot_list(self, client, team_setup):
        out = team_setup["outsider_token"]
        pid = team_setup["project_id"]
        assert client.get(f"/projects/{pid}/tasks", headers=auth(out)).status_code == 403

    def test_tasks_isolated_to_project(self, client, team_setup):
        mgr = team_setup["manager_token"]
        team_id = team_setup["team_id"]
        pid_a = team_setup["project_id"]
        # Create second project in same team
        pid_b = client.post(f"/teams/{team_id}/projects", headers=auth(mgr),
                             json={"name": "Project B"}).json()["id"]
        client.post(f"/projects/{pid_a}/tasks", headers=auth(mgr), json={"title": "A task"})
        client.post(f"/projects/{pid_b}/tasks", headers=auth(mgr), json={"title": "B task"})
        a_titles = [t["title"] for t in client.get(f"/projects/{pid_a}/tasks", headers=auth(mgr)).json()["items"]]
        b_titles = [t["title"] for t in client.get(f"/projects/{pid_b}/tasks", headers=auth(mgr)).json()["items"]]
        assert "B task" not in a_titles
        assert "A task" not in b_titles


class TestProjectTaskGet:
    def test_member_can_get(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem = team_setup["member_token"]
        pid = team_setup["project_id"]
        task_id = client.post(f"/projects/{pid}/tasks", headers=auth(mgr), json={"title": "T"}).json()["id"]
        assert client.get(f"/tasks/{task_id}", headers=auth(mem)).status_code == 200

    def test_outsider_cannot_get(self, client, team_setup):
        mgr = team_setup["manager_token"]
        out = team_setup["outsider_token"]
        pid = team_setup["project_id"]
        task_id = client.post(f"/projects/{pid}/tasks", headers=auth(mgr), json={"title": "T"}).json()["id"]
        assert client.get(f"/tasks/{task_id}", headers=auth(out)).status_code == 403

    def test_nonexistent_returns_404(self, client, team_setup):
        assert client.get(f"/tasks/{uuid4()}", headers=auth(team_setup["manager_token"])).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TASK UPDATE
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectTaskUpdate:
    def _proj_task(self, client, mgr_token, pid, mem_id=None):
        body = {"title": "Work item"}
        if mem_id:
            body["assigned_to"] = str(mem_id)
        return client.post(f"/projects/{pid}/tasks", headers=auth(mgr_token), json=body).json()["id"]

    def test_manager_can_update(self, client, team_setup):
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        res = client.patch(f"/tasks/{task_id}", headers=auth(mgr), json={"title": "New title"})
        assert res.status_code == 200
        assert res.json()["title"] == "New title"

    def test_assignee_can_update_status(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem = team_setup["member_token"]
        mem_id = me(client, mem)["id"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid, mem_id=mem_id)
        res = client.patch(f"/tasks/{task_id}", headers=auth(mem), json={"status": "IN_PROGRESS"})
        assert res.status_code == 200
        assert res.json()["status"] == "IN_PROGRESS"

    def test_assignee_can_complete(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem = team_setup["member_token"]
        mem_id = me(client, mem)["id"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid, mem_id=mem_id)
        res = client.patch(f"/tasks/{task_id}", headers=auth(mem), json={"status": "COMPLETED"})
        assert res.status_code == 200
        assert res.json()["completed_at"] is not None

    def test_non_assigned_member_cannot_update(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem = team_setup["member_token"]
        pid = team_setup["project_id"]
        # task with NO assignee
        task_id = self._proj_task(client, mgr, pid)
        assert client.patch(f"/tasks/{task_id}", headers=auth(mem), json={"title": "nope"}).status_code == 403

    def test_outsider_cannot_update(self, client, team_setup):
        mgr = team_setup["manager_token"]
        out = team_setup["outsider_token"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        assert client.patch(f"/tasks/{task_id}", headers=auth(out), json={"title": "nope"}).status_code == 403

    def test_nonexistent_returns_404(self, client, team_setup):
        mgr = team_setup["manager_token"]
        assert client.patch(f"/tasks/{uuid4()}", headers=auth(mgr), json={"title": "x"}).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# ASSIGNMENT ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskAssignment:
    def _proj_task(self, client, mgr_token, pid):
        return client.post(f"/projects/{pid}/tasks", headers=auth(mgr_token),
                           json={"title": "Assign me"}).json()["id"]

    def test_manager_can_assign(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem_id = me(client, team_setup["member_token"])["id"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        res = client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                           json={"assigned_to": str(mem_id)})
        assert res.status_code == 200
        assert res.json()["assigned_to"] == str(mem_id)

    def test_manager_can_reassign(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mgr_id = me(client, mgr)["id"]
        mem_id = me(client, team_setup["member_token"])["id"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                     json={"assigned_to": str(mem_id)})
        # reassign to manager themselves
        res = client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                           json={"assigned_to": str(mgr_id)})
        assert res.status_code == 200
        assert res.json()["assigned_to"] == str(mgr_id)

    def test_manager_can_unassign(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem_id = me(client, team_setup["member_token"])["id"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                     json={"assigned_to": str(mem_id)})
        res = client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                           json={"assigned_to": None})
        assert res.status_code == 200
        assert res.json()["assigned_to"] is None

    def test_normal_member_cannot_assign(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem = team_setup["member_token"]
        mem_id = me(client, mem)["id"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        assert client.patch(f"/tasks/{task_id}/assignment", headers=auth(mem),
                            json={"assigned_to": str(mem_id)}).status_code == 403

    def test_assignee_cannot_reassign(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem = team_setup["member_token"]
        mem_id = me(client, mem)["id"]
        mgr_id = me(client, mgr)["id"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        # assign to member
        client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                     json={"assigned_to": str(mem_id)})
        # member (assignee) tries to reassign
        assert client.patch(f"/tasks/{task_id}/assignment", headers=auth(mem),
                            json={"assigned_to": str(mgr_id)}).status_code == 403

    def test_cross_team_user_rejected(self, client, team_setup):
        mgr = team_setup["manager_token"]
        out_id = me(client, team_setup["outsider_token"])["id"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        assert client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                            json={"assigned_to": str(out_id)}).status_code == 400

    def test_nonexistent_user_rejected(self, client, team_setup):
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        assert client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                            json={"assigned_to": str(uuid4())}).status_code == 404

    def test_inactive_user_rejected(self, client, team_setup, db_session):
        from app.models.user import User
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        inactive_token = register_and_login(client, "task_inact_assign@example.com")
        inactive_id = me(client, inactive_token)["id"]
        team_id = team_setup["team_id"]
        client.post(f"/teams/{team_id}/members", headers=auth(mgr),
                    json={"email": "task_inact_assign@example.com", "role": "MEMBER"})
        u = db_session.query(User).filter(User.email == "task_inact_assign@example.com").first()
        u.is_active = False
        db_session.commit()
        assert client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                            json={"assigned_to": str(inactive_id)}).status_code == 400

    def test_personal_task_cannot_be_assigned(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem_id = me(client, team_setup["member_token"])["id"]
        # personal task
        task_id = client.post("/tasks", headers=auth(mgr), json={"title": "personal"}).json()["id"]
        assert client.patch(f"/tasks/{task_id}/assignment", headers=auth(mgr),
                            json={"assigned_to": str(mem_id)}).status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TASK DELETE
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectTaskDelete:
    def _proj_task(self, client, mgr_token, pid, assigned_to=None):
        body = {"title": "Delete me"}
        if assigned_to:
            body["assigned_to"] = str(assigned_to)
        return client.post(f"/projects/{pid}/tasks", headers=auth(mgr_token), json=body).json()["id"]

    def test_manager_can_delete(self, client, team_setup):
        mgr = team_setup["manager_token"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        assert client.delete(f"/tasks/{task_id}", headers=auth(mgr)).status_code == 204
        assert client.get(f"/tasks/{task_id}", headers=auth(mgr)).status_code == 404

    def test_assignee_alone_cannot_delete(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem = team_setup["member_token"]
        mem_id = me(client, mem)["id"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid, assigned_to=mem_id)
        assert client.delete(f"/tasks/{task_id}", headers=auth(mem)).status_code == 403

    def test_ordinary_member_cannot_delete(self, client, team_setup):
        mgr = team_setup["manager_token"]
        mem = team_setup["member_token"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        assert client.delete(f"/tasks/{task_id}", headers=auth(mem)).status_code == 403

    def test_outsider_cannot_delete(self, client, team_setup):
        mgr = team_setup["manager_token"]
        out = team_setup["outsider_token"]
        pid = team_setup["project_id"]
        task_id = self._proj_task(client, mgr, pid)
        assert client.delete(f"/tasks/{task_id}", headers=auth(out)).status_code == 403

    def test_nonexistent_returns_404(self, client, team_setup):
        mgr = team_setup["manager_token"]
        assert client.delete(f"/tasks/{uuid4()}", headers=auth(mgr)).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskSecurity:
    def test_no_password_hash_in_response(self, client):
        token = register_and_login(client, "sec_ph@example.com")
        task_id = client.post("/tasks", headers=auth(token), json={"title": "sec"}).json()["id"]
        for endpoint in ["/tasks", f"/tasks/{task_id}"]:
            res = client.get(endpoint, headers=auth(token)).json()
            if isinstance(res, dict) and "items" in res:
                items = res["items"]
            else:
                items = res if isinstance(res, list) else [res]
            for item in items:
                assert "password_hash" not in item
                assert "password" not in item

    def test_uuid_knowledge_does_not_bypass_personal_auth(self, client):
        t1 = register_and_login(client, "sec_uuid_a@example.com")
        t2 = register_and_login(client, "sec_uuid_b@example.com")
        task_id = client.post("/tasks", headers=auth(t1), json={"title": "secret"}).json()["id"]
        assert client.get(f"/tasks/{task_id}", headers=auth(t2)).status_code == 403
        assert client.patch(f"/tasks/{task_id}", headers=auth(t2), json={"title": "hacked"}).status_code == 403
        assert client.delete(f"/tasks/{task_id}", headers=auth(t2)).status_code == 403

    def test_uuid_knowledge_does_not_bypass_project_auth(self, client, team_setup):
        mgr = team_setup["manager_token"]
        out = team_setup["outsider_token"]
        pid = team_setup["project_id"]
        task_id = client.post(f"/projects/{pid}/tasks", headers=auth(mgr),
                              json={"title": "hidden"}).json()["id"]
        assert client.get(f"/tasks/{task_id}", headers=auth(out)).status_code == 403
        assert client.patch(f"/tasks/{task_id}", headers=auth(out), json={"title": "hacked"}).status_code == 403
        assert client.delete(f"/tasks/{task_id}", headers=auth(out)).status_code == 403
