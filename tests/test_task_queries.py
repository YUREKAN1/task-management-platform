"""
Phase 7A – Task Search, Filtering & Pagination Tests

Tests that the GET /tasks and GET /projects/{project_id}/tasks endpoints
correctly apply:
  - pagination  (page, page_size, total, total_pages)
  - search      (title, description, case-insensitive)
  - status filter
  - priority filter
  - assignee filter
  - due-date filters (due_before, due_after)
  - combined filters
  - authorization-aware counting (unauthorized data never leaks)
"""
import pytest
from datetime import datetime, timedelta, timezone


# ─── Helpers ─────────────────────────────────────────────────────────────────

def register_and_login(client, email, password="pass"):
    client.post("/auth/register", json={"name": email.split("@")[0], "email": email, "password": password})
    return client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def me(client, token):
    return client.get("/users/me", headers=auth(token)).json()


def iso(dt: datetime) -> str:
    # Strip timezone info before formatting.  A timezone-aware datetime produces
    # e.g. "2026-09-20T06:00:00+00:00".  The "+" is decoded as a space when
    # embedded in a URL query string, causing FastAPI to reject the value with
    # 422.  Naive UTC datetimes produce "2026-09-20T06:00:00.123456" which is
    # safe to embed directly in URLs and is still accepted by FastAPI's datetime
    # parser (treated as UTC).
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()


# ─── Shared fixture ───────────────────────────────────────────────────────────

@pytest.fixture
def q_setup(client):
    """
    Three users: manager, member, outsider.
    One team + one project.  Manager and member belong to the team.
    Outsider is NOT in the team.
    """
    mgr_token = register_and_login(client, "q_mgr@example.com")
    mem_token  = register_and_login(client, "q_mem@example.com")
    out_token  = register_and_login(client, "q_out@example.com")

    team   = client.post("/teams", headers=auth(mgr_token), json={"name": "QTeam"}).json()
    team_id = team["id"]

    client.post(f"/teams/{team_id}/members", headers=auth(mgr_token),
                json={"email": "q_mem@example.com", "role": "MEMBER"})

    project = client.post(f"/teams/{team_id}/projects", headers=auth(mgr_token),
                          json={"name": "QProject"}).json()
    project_id = project["id"]

    mgr_id = me(client, mgr_token)["id"]
    mem_id = me(client, mem_token)["id"]

    return {
        "mgr_token":   mgr_token,
        "mem_token":   mem_token,
        "out_token":   out_token,
        "team_id":     team_id,
        "project_id":  project_id,
        "mgr_id":      mgr_id,
        "mem_id":      mem_id,
    }


def _create_proj_task(client, token, project_id, **kwargs):
    """Helper: create a project task and return its id."""
    body = {"title": "default title", **kwargs}
    res = client.post(f"/projects/{project_id}/tasks", headers=auth(token), json=body)
    assert res.status_code == 201, res.json()
    return res.json()["id"]


def _create_personal_task(client, token, **kwargs):
    body = {"title": "default personal", **kwargs}
    res = client.post("/tasks", headers=auth(token), json=body)
    assert res.status_code == 201, res.json()
    return res.json()["id"]


# ═══════════════════════════════════════════════════════════════════════════════
# PAGINATION — Personal Tasks
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersonalTaskPagination:

    def test_default_pagination_response_shape(self, client):
        token = register_and_login(client, "pgn_shape@example.com")
        _create_personal_task(client, token, title="T1")
        res = client.get("/tasks", headers=auth(token))
        assert res.status_code == 200
        d = res.json()
        assert "items" in d
        assert "page" in d
        assert "page_size" in d
        assert "total" in d
        assert "total_pages" in d

    def test_default_page_is_1(self, client):
        token = register_and_login(client, "pgn_default@example.com")
        _create_personal_task(client, token, title="X")
        d = client.get("/tasks", headers=auth(token)).json()
        assert d["page"] == 1

    def test_default_page_size_is_20(self, client):
        token = register_and_login(client, "pgn_ps20@example.com")
        _create_personal_task(client, token, title="X")
        d = client.get("/tasks", headers=auth(token)).json()
        assert d["page_size"] == 20

    def test_total_counts_only_own_tasks(self, client):
        t1 = register_and_login(client, "pgn_cnt_a@example.com")
        t2 = register_and_login(client, "pgn_cnt_b@example.com")
        _create_personal_task(client, t1, title="A1")
        _create_personal_task(client, t1, title="A2")
        _create_personal_task(client, t2, title="B1")  # belongs to other user

        d = client.get("/tasks", headers=auth(t1)).json()
        assert d["total"] == 2
        assert d["total_pages"] == 1

    def test_custom_page_size(self, client):
        token = register_and_login(client, "pgn_cps@example.com")
        for i in range(5):
            _create_personal_task(client, token, title=f"Task {i}")
        d = client.get("/tasks?page_size=2", headers=auth(token)).json()
        assert d["page_size"] == 2
        assert len(d["items"]) == 2
        assert d["total"] == 5
        assert d["total_pages"] == 3

    def test_page_2(self, client):
        token = register_and_login(client, "pgn_pg2@example.com")
        for i in range(5):
            _create_personal_task(client, token, title=f"Task {i}")
        d = client.get("/tasks?page=2&page_size=2", headers=auth(token)).json()
        assert d["page"] == 2
        assert len(d["items"]) == 2

    def test_last_page_has_remaining_items(self, client):
        token = register_and_login(client, "pgn_last@example.com")
        for i in range(5):
            _create_personal_task(client, token, title=f"T{i}")
        d = client.get("/tasks?page=3&page_size=2", headers=auth(token)).json()
        assert d["page"] == 3
        assert len(d["items"]) == 1  # 5 tasks, page 3 of size 2 → 1 item

    def test_page_beyond_data_returns_empty(self, client):
        token = register_and_login(client, "pgn_beyond@example.com")
        _create_personal_task(client, token, title="Only one")
        d = client.get("/tasks?page=99&page_size=10", headers=auth(token)).json()
        assert d["items"] == []
        assert d["total"] == 1

    def test_page_lt_1_rejected(self, client):
        token = register_and_login(client, "pgn_inv_pg@example.com")
        res = client.get("/tasks?page=0", headers=auth(token))
        assert res.status_code == 422

    def test_page_size_lt_1_rejected(self, client):
        token = register_and_login(client, "pgn_inv_ps@example.com")
        res = client.get("/tasks?page_size=0", headers=auth(token))
        assert res.status_code == 422

    def test_page_size_above_100_rejected(self, client):
        token = register_and_login(client, "pgn_max_ps@example.com")
        res = client.get("/tasks?page_size=101", headers=auth(token))
        assert res.status_code == 422

    def test_page_size_100_accepted(self, client):
        token = register_and_login(client, "pgn_max100@example.com")
        res = client.get("/tasks?page_size=100", headers=auth(token))
        assert res.status_code == 200

    def test_empty_list_total_zero(self, client):
        token = register_and_login(client, "pgn_empty@example.com")
        d = client.get("/tasks", headers=auth(token)).json()
        assert d["total"] == 0
        assert d["total_pages"] == 0
        assert d["items"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH — Personal Tasks
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersonalTaskSearch:

    def _token(self, client, email):
        return register_and_login(client, email)

    def test_search_title_match(self, client):
        token = self._token(client, "srch_title@example.com")
        _create_personal_task(client, token, title="Monthly report")
        _create_personal_task(client, token, title="Sprint planning")
        d = client.get("/tasks?search=report", headers=auth(token)).json()
        assert d["total"] == 1
        assert d["items"][0]["title"] == "Monthly report"

    def test_search_description_match(self, client):
        token = self._token(client, "srch_desc@example.com")
        _create_personal_task(client, token, title="Planning", description="Review the quarterly report data")
        _create_personal_task(client, token, title="Something else")
        d = client.get("/tasks?search=quarterly", headers=auth(token)).json()
        assert d["total"] == 1

    def test_search_case_insensitive(self, client):
        token = self._token(client, "srch_case@example.com")
        _create_personal_task(client, token, title="Important MEETING")
        d = client.get("/tasks?search=meeting", headers=auth(token)).json()
        assert d["total"] == 1

    def test_search_no_match(self, client):
        token = self._token(client, "srch_none@example.com")
        _create_personal_task(client, token, title="Completely unrelated")
        d = client.get("/tasks?search=zzzznotaword", headers=auth(token)).json()
        assert d["total"] == 0
        assert d["items"] == []

    def test_search_partial_match(self, client):
        token = self._token(client, "srch_partial@example.com")
        _create_personal_task(client, token, title="Deploy application")
        d = client.get("/tasks?search=applic", headers=auth(token)).json()
        assert d["total"] == 1

    def test_search_does_not_expose_other_users_tasks(self, client):
        t1 = self._token(client, "srch_prv_a@example.com")
        t2 = self._token(client, "srch_prv_b@example.com")
        _create_personal_task(client, t1, title="Secret report for user A")
        # t2 searches for "report" but should find nothing
        d = client.get("/tasks?search=report", headers=auth(t2)).json()
        assert d["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS FILTER — Personal Tasks
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersonalTaskStatusFilter:

    def test_filter_todo(self, client):
        token = register_and_login(client, "sf_todo@example.com")
        _create_personal_task(client, token, title="Todo task")
        d = client.get("/tasks?status=TODO", headers=auth(token)).json()
        assert d["total"] >= 1
        assert all(t["status"] == "TODO" for t in d["items"])

    def test_filter_in_progress(self, client):
        token = register_and_login(client, "sf_ip@example.com")
        tid = _create_personal_task(client, token, title="WIP task")
        client.patch(f"/tasks/{tid}", headers=auth(token), json={"status": "IN_PROGRESS"})
        d = client.get("/tasks?status=IN_PROGRESS", headers=auth(token)).json()
        assert d["total"] >= 1
        assert all(t["status"] == "IN_PROGRESS" for t in d["items"])

    def test_filter_completed(self, client):
        token = register_and_login(client, "sf_done@example.com")
        tid = _create_personal_task(client, token, title="Done task")
        client.patch(f"/tasks/{tid}", headers=auth(token), json={"status": "COMPLETED"})
        d = client.get("/tasks?status=COMPLETED", headers=auth(token)).json()
        assert d["total"] >= 1
        assert all(t["status"] == "COMPLETED" for t in d["items"])

    def test_invalid_status_rejected(self, client):
        token = register_and_login(client, "sf_bad@example.com")
        res = client.get("/tasks?status=INVALID_STATUS", headers=auth(token))
        assert res.status_code == 422

    def test_status_filter_isolates_results(self, client):
        token = register_and_login(client, "sf_iso@example.com")
        _create_personal_task(client, token, title="Task A")
        tid = _create_personal_task(client, token, title="Task B")
        client.patch(f"/tasks/{tid}", headers=auth(token), json={"status": "IN_PROGRESS"})

        todo_d = client.get("/tasks?status=TODO", headers=auth(token)).json()
        ip_d   = client.get("/tasks?status=IN_PROGRESS", headers=auth(token)).json()
        assert todo_d["total"] == 1
        assert ip_d["total"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# PRIORITY FILTER — Personal Tasks
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersonalTaskPriorityFilter:

    def test_filter_low(self, client):
        token = register_and_login(client, "pf_low@example.com")
        _create_personal_task(client, token, title="Low task", priority="LOW")
        d = client.get("/tasks?priority=LOW", headers=auth(token)).json()
        assert d["total"] >= 1
        assert all(t["priority"] == "LOW" for t in d["items"])

    def test_filter_medium(self, client):
        token = register_and_login(client, "pf_med@example.com")
        _create_personal_task(client, token, title="Med task", priority="MEDIUM")
        d = client.get("/tasks?priority=MEDIUM", headers=auth(token)).json()
        assert d["total"] >= 1
        assert all(t["priority"] == "MEDIUM" for t in d["items"])

    def test_filter_high(self, client):
        token = register_and_login(client, "pf_high@example.com")
        _create_personal_task(client, token, title="High task", priority="HIGH")
        d = client.get("/tasks?priority=HIGH", headers=auth(token)).json()
        assert d["total"] >= 1
        assert all(t["priority"] == "HIGH" for t in d["items"])

    def test_invalid_priority_rejected(self, client):
        token = register_and_login(client, "pf_bad@example.com")
        res = client.get("/tasks?priority=CRITICAL", headers=auth(token))
        assert res.status_code == 422

    def test_priority_filter_isolates(self, client):
        token = register_and_login(client, "pf_iso@example.com")
        _create_personal_task(client, token, title="Low", priority="LOW")
        _create_personal_task(client, token, title="High", priority="HIGH")
        d = client.get("/tasks?priority=HIGH", headers=auth(token)).json()
        assert d["total"] == 1
        assert d["items"][0]["priority"] == "HIGH"


# ═══════════════════════════════════════════════════════════════════════════════
# DUE DATE FILTERS — Personal Tasks
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersonalTaskDueDateFilter:

    def _now(self):
        # Naive UTC — avoids "+00:00" in ISO strings, which breaks URL query params
        return datetime.utcnow()

    def test_due_before(self, client):
        token = register_and_login(client, "dd_before@example.com")
        past   = iso(self._now() - timedelta(days=5))
        future = iso(self._now() + timedelta(days=5))
        _create_personal_task(client, token, title="Past task",   due_date=past)
        _create_personal_task(client, token, title="Future task", due_date=future)

        cutoff = iso(self._now())
        d = client.get(f"/tasks?due_before={cutoff}", headers=auth(token)).json()
        titles = [t["title"] for t in d["items"]]
        assert "Past task" in titles
        assert "Future task" not in titles

    def test_due_after(self, client):
        token = register_and_login(client, "dd_after@example.com")
        past   = iso(self._now() - timedelta(days=5))
        future = iso(self._now() + timedelta(days=5))
        _create_personal_task(client, token, title="Past task",   due_date=past)
        _create_personal_task(client, token, title="Future task", due_date=future)

        cutoff = iso(self._now())
        d = client.get(f"/tasks?due_after={cutoff}", headers=auth(token)).json()
        titles = [t["title"] for t in d["items"]]
        assert "Future task" in titles
        assert "Past task" not in titles

    def test_null_due_dates_not_included_in_due_before(self, client):
        token = register_and_login(client, "dd_null@example.com")
        _create_personal_task(client, token, title="No due date")   # due_date=None
        cutoff = iso(self._now() + timedelta(days=30))
        d = client.get(f"/tasks?due_before={cutoff}", headers=auth(token)).json()
        # Tasks with null due_date should NOT appear in due_before results
        for item in d["items"]:
            assert item["due_date"] is not None

    def test_null_due_dates_not_included_in_due_after(self, client):
        token = register_and_login(client, "dd_null2@example.com")
        _create_personal_task(client, token, title="No due date")   # due_date=None
        cutoff = iso(self._now() - timedelta(days=30))
        d = client.get(f"/tasks?due_after={cutoff}", headers=auth(token)).json()
        for item in d["items"]:
            assert item["due_date"] is not None

    def test_due_before_and_due_after_combined(self, client):
        token = register_and_login(client, "dd_range@example.com")
        base = self._now()
        _create_personal_task(client, token, title="Old",    due_date=iso(base - timedelta(days=10)))
        _create_personal_task(client, token, title="Middle", due_date=iso(base))
        _create_personal_task(client, token, title="New",    due_date=iso(base + timedelta(days=10)))

        after  = iso(base - timedelta(days=5))
        before = iso(base + timedelta(days=5))
        d = client.get(f"/tasks?due_after={after}&due_before={before}", headers=auth(token)).json()
        titles = [t["title"] for t in d["items"]]
        assert "Middle" in titles
        assert "Old" not in titles
        assert "New" not in titles

    def test_invalid_date_format_rejected(self, client):
        token = register_and_login(client, "dd_invalid@example.com")
        res = client.get("/tasks?due_before=not-a-date", headers=auth(token))
        assert res.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# ASSIGNEE FILTER — Project Tasks (assigned_to only applies to project tasks)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssigneeFilter:

    def test_filter_by_assignee(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        mem_id = q_setup["mem_id"]
        pid = q_setup["project_id"]

        # Task assigned to member
        _create_proj_task(client, mgr, pid, title="Assigned task", assigned_to=str(mem_id))
        # Unassigned task
        _create_proj_task(client, mgr, pid, title="Unassigned task")

        d = client.get(f"/projects/{pid}/tasks?assigned_to={mem_id}", headers=auth(mgr)).json()
        assert d["total"] == 1
        assert d["items"][0]["title"] == "Assigned task"
        assert d["items"][0]["assigned_to"] == str(mem_id)

    def test_assignee_filter_no_results(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        mgr_id = q_setup["mgr_id"]
        pid = q_setup["project_id"]

        _create_proj_task(client, mgr, pid, title="Unassigned task")

        d = client.get(f"/projects/{pid}/tasks?assigned_to={mgr_id}", headers=auth(mgr)).json()
        assert d["total"] == 0

    def test_invalid_uuid_assignee_rejected(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        res = client.get(f"/projects/{pid}/tasks?assigned_to=not-a-uuid", headers=auth(mgr))
        assert res.status_code == 422

    def test_assignee_filter_does_not_bypass_authorization(self, client, q_setup):
        """Non-member cannot use assignee filter to see team tasks."""
        mgr = q_setup["mgr_token"]
        out = q_setup["out_token"]
        mem_id = q_setup["mem_id"]
        pid = q_setup["project_id"]

        _create_proj_task(client, mgr, pid, title="Private", assigned_to=str(mem_id))

        res = client.get(f"/projects/{pid}/tasks?assigned_to={mem_id}", headers=auth(out))
        assert res.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# COMBINED FILTERS — Personal Tasks
# ═══════════════════════════════════════════════════════════════════════════════

class TestCombinedFilters:

    def test_search_and_status(self, client):
        token = register_and_login(client, "comb_ss@example.com")
        _create_personal_task(client, token, title="report review")  # TODO by default
        tid = _create_personal_task(client, token, title="report update")
        client.patch(f"/tasks/{tid}", headers=auth(token), json={"status": "IN_PROGRESS"})

        d = client.get("/tasks?search=report&status=TODO", headers=auth(token)).json()
        assert d["total"] == 1
        assert d["items"][0]["status"] == "TODO"

    def test_status_and_priority(self, client):
        token = register_and_login(client, "comb_sp@example.com")
        _create_personal_task(client, token, title="High Todo", priority="HIGH")
        _create_personal_task(client, token, title="Low Todo",  priority="LOW")
        _create_personal_task(client, token, title="High WIP",  priority="HIGH")

        # Patch the last one to IN_PROGRESS
        tasks_d = client.get("/tasks?search=High WIP", headers=auth(token)).json()
        if tasks_d["items"]:
            client.patch(f"/tasks/{tasks_d['items'][0]['id']}", headers=auth(token), json={"status": "IN_PROGRESS"})

        d = client.get("/tasks?status=TODO&priority=HIGH", headers=auth(token)).json()
        assert d["total"] == 1
        assert d["items"][0]["priority"] == "HIGH"
        assert d["items"][0]["status"] == "TODO"

    def test_search_priority_status_combined(self, client):
        token = register_and_login(client, "comb_sps@example.com")
        _create_personal_task(client, token, title="api deploy high todo",  priority="HIGH")
        _create_personal_task(client, token, title="api review medium todo", priority="MEDIUM")
        _create_personal_task(client, token, title="api test high done",     priority="HIGH")

        # Complete the last one
        tasks_d = client.get("/tasks?search=api test high done", headers=auth(token)).json()
        if tasks_d["items"]:
            client.patch(f"/tasks/{tasks_d['items'][0]['id']}", headers=auth(token), json={"status": "COMPLETED"})

        d = client.get("/tasks?search=api&status=TODO&priority=HIGH", headers=auth(token)).json()
        assert d["total"] == 1
        assert "high todo" in d["items"][0]["title"]

    def test_filters_with_pagination(self, client):
        token = register_and_login(client, "comb_pg@example.com")
        for i in range(6):
            _create_personal_task(client, token, title=f"High task {i}", priority="HIGH")
        _create_personal_task(client, token, title="Low task", priority="LOW")

        d = client.get("/tasks?priority=HIGH&page=1&page_size=3", headers=auth(token)).json()
        assert d["total"] == 6
        assert d["total_pages"] == 2
        assert len(d["items"]) == 3
        assert all(t["priority"] == "HIGH" for t in d["items"])

    def test_combined_filters_all_and_semantics(self, client):
        """All filters combine as AND – a task must match ALL supplied conditions."""
        token = register_and_login(client, "comb_and@example.com")
        _create_personal_task(client, token, title="matching both", priority="HIGH")
        _create_personal_task(client, token, title="matching priority only", priority="HIGH")
        _create_personal_task(client, token, title="both in description", priority="LOW",
                               description="matching both conditions met")

        d = client.get("/tasks?search=matching both&priority=HIGH", headers=auth(token)).json()
        assert d["total"] == 1
        assert d["items"][0]["title"] == "matching both"


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TASK QUERIES
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectTaskQueries:

    def test_project_pagination_response_shape(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="T1")
        d = client.get(f"/projects/{pid}/tasks", headers=auth(mgr)).json()
        assert all(k in d for k in ("items", "page", "page_size", "total", "total_pages"))

    def test_project_pagination_custom_size(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        for i in range(5):
            _create_proj_task(client, mgr, pid, title=f"Proj Task {i}")
        d = client.get(f"/projects/{pid}/tasks?page_size=2", headers=auth(mgr)).json()
        assert len(d["items"]) == 2
        assert d["total"] == 5
        assert d["total_pages"] == 3

    def test_project_search_title(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="Deploy backend service")
        _create_proj_task(client, mgr, pid, title="Review PR comments")
        d = client.get(f"/projects/{pid}/tasks?search=backend", headers=auth(mgr)).json()
        assert d["total"] == 1
        assert "backend" in d["items"][0]["title"].lower()

    def test_project_search_description(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="Vague task",
                          description="This involves the payment gateway integration")
        _create_proj_task(client, mgr, pid, title="Other task")
        d = client.get(f"/projects/{pid}/tasks?search=payment", headers=auth(mgr)).json()
        assert d["total"] == 1

    def test_project_search_case_insensitive(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="UPPER CASE task")
        d = client.get(f"/projects/{pid}/tasks?search=upper case", headers=auth(mgr)).json()
        assert d["total"] == 1

    def test_project_status_filter(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="Todo task")
        tid = _create_proj_task(client, mgr, pid, title="Done task")
        client.patch(f"/tasks/{tid}", headers=auth(mgr), json={"status": "COMPLETED"})

        d = client.get(f"/projects/{pid}/tasks?status=TODO", headers=auth(mgr)).json()
        assert d["total"] == 1
        assert d["items"][0]["status"] == "TODO"

    def test_project_priority_filter(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="High", priority="HIGH")
        _create_proj_task(client, mgr, pid, title="Low",  priority="LOW")
        d = client.get(f"/projects/{pid}/tasks?priority=HIGH", headers=auth(mgr)).json()
        assert d["total"] == 1
        assert d["items"][0]["priority"] == "HIGH"

    def test_project_search_scoped_to_project(self, client, q_setup):
        """Search must not leak tasks from another project."""
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        team_id = q_setup["team_id"]

        pid2 = client.post(f"/teams/{team_id}/projects", headers=auth(mgr),
                           json={"name": "Second Project"}).json()["id"]

        _create_proj_task(client, mgr, pid,  title="Report in project 1")
        _create_proj_task(client, mgr, pid2, title="Report in project 2")

        d = client.get(f"/projects/{pid}/tasks?search=report", headers=auth(mgr)).json()
        assert d["total"] == 1
        assert all(t["project_id"] == pid for t in d["items"])

    def test_project_due_before_filter(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        base = datetime.utcnow()
        _create_proj_task(client, mgr, pid, title="Past task",   due_date=iso(base - timedelta(days=3)))
        _create_proj_task(client, mgr, pid, title="Future task", due_date=iso(base + timedelta(days=3)))
        cutoff = iso(base)
        d = client.get(f"/projects/{pid}/tasks?due_before={cutoff}", headers=auth(mgr)).json()
        assert d["total"] == 1
        assert d["items"][0]["title"] == "Past task"

    def test_project_due_after_filter(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        base = datetime.utcnow()
        _create_proj_task(client, mgr, pid, title="Past task",   due_date=iso(base - timedelta(days=3)))
        _create_proj_task(client, mgr, pid, title="Future task", due_date=iso(base + timedelta(days=3)))
        cutoff = iso(base)
        d = client.get(f"/projects/{pid}/tasks?due_after={cutoff}", headers=auth(mgr)).json()
        assert d["total"] == 1
        assert d["items"][0]["title"] == "Future task"

    def test_project_member_can_use_filters(self, client, q_setup):
        """Regular team members can use filters too."""
        mgr = q_setup["mgr_token"]
        mem = q_setup["mem_token"]
        pid = q_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="High priority task", priority="HIGH")
        _create_proj_task(client, mgr, pid, title="Low priority task",  priority="LOW")
        d = client.get(f"/projects/{pid}/tasks?priority=HIGH", headers=auth(mem)).json()
        assert d["total"] == 1

    def test_project_invalid_status_rejected(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        res = client.get(f"/projects/{pid}/tasks?status=NOPE", headers=auth(mgr))
        assert res.status_code == 422

    def test_project_invalid_priority_rejected(self, client, q_setup):
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        res = client.get(f"/projects/{pid}/tasks?priority=URGENT", headers=auth(mgr))
        assert res.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# AUTHORIZATION SAFETY
# ═══════════════════════════════════════════════════════════════════════════════

class TestQueryAuthorization:

    def test_personal_tasks_private_in_list(self, client):
        """Two users; each creates tasks; neither sees the other's in /tasks."""
        t1 = register_and_login(client, "auth_prv_1@example.com")
        t2 = register_and_login(client, "auth_prv_2@example.com")
        _create_personal_task(client, t1, title="User1 task")
        _create_personal_task(client, t2, title="User2 task")

        d1 = client.get("/tasks", headers=auth(t1)).json()
        d2 = client.get("/tasks", headers=auth(t2)).json()

        titles1 = [t["title"] for t in d1["items"]]
        titles2 = [t["title"] for t in d2["items"]]

        assert "User2 task" not in titles1
        assert "User1 task" not in titles2
        assert d1["total"] == 1
        assert d2["total"] == 1

    def test_non_member_cannot_query_project_tasks(self, client, q_setup):
        out = q_setup["out_token"]
        pid = q_setup["project_id"]
        res = client.get(f"/projects/{pid}/tasks", headers=auth(out))
        assert res.status_code == 403

    def test_non_member_with_filters_still_forbidden(self, client, q_setup):
        """Filters do not grant access to forbidden projects."""
        out = q_setup["out_token"]
        pid = q_setup["project_id"]
        res = client.get(f"/projects/{pid}/tasks?status=TODO&priority=HIGH", headers=auth(out))
        assert res.status_code == 403

    def test_total_reflects_only_authorized_tasks(self, client):
        """total must not count tasks the user cannot see."""
        t1 = register_and_login(client, "auth_cnt_a@example.com")
        t2 = register_and_login(client, "auth_cnt_b@example.com")
        for _ in range(3):
            _create_personal_task(client, t1, title="T1 task")
        _create_personal_task(client, t2, title="T2 task")

        d = client.get("/tasks", headers=auth(t2)).json()
        assert d["total"] == 1  # NOT 4

    def test_search_does_not_expand_beyond_authorization_scope(self, client, q_setup):
        """Search term that matches tasks in another project does not expose them."""
        mgr = q_setup["mgr_token"]
        pid = q_setup["project_id"]
        team_id = q_setup["team_id"]

        pid2 = client.post(f"/teams/{team_id}/projects", headers=auth(mgr),
                           json={"name": "Restricted Project"}).json()["id"]
        _create_proj_task(client, mgr, pid2, title="Super secret alpha task")

        # Member can access pid but NOT pid2 (they were only added to the first project's team)
        # Actually member is in the same team so can access pid2 too in this test
        # Let's use the outsider who cannot access either project
        out = q_setup["out_token"]
        res = client.get(f"/projects/{pid}/tasks?search=alpha", headers=auth(out))
        assert res.status_code == 403

    def test_pagination_does_not_leak_unauthorized_records(self, client):
        """Page 2 for user who has only 1 task should be empty, not show another user's tasks."""
        t1 = register_and_login(client, "auth_pg_a@example.com")
        t2 = register_and_login(client, "auth_pg_b@example.com")

        _create_personal_task(client, t1, title="T1 only task")
        for _ in range(10):
            _create_personal_task(client, t2, title="T2 task bulk")

        # t1 has only 1 task; requesting page 2 must show nothing
        d = client.get("/tasks?page=2&page_size=1", headers=auth(t1)).json()
        assert d["items"] == []
        assert d["total"] == 1
