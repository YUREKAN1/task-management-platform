"""
Phase 7B – Sorting & Query Refinement Tests

Tests that the GET /tasks and GET /projects/{project_id}/tasks endpoints
correctly handle:
  - sort_by (all six whitelisted fields)
  - sort_order (asc / desc)
  - invalid sort_by / sort_order values (expect 422)
  - default ordering (created_at desc)
  - tie-breaking determinism
  - due_date NULLs during sorting
  - sorting combined with Phase 7A filters
  - sorting combined with pagination
  - project-scoped sorting
  - authorization remains intact during sorting
"""
import pytest
import time
from datetime import datetime, timedelta


# ─── Helpers ─────────────────────────────────────────────────────────────────

def register_and_login(client, email, password="pass"):
    client.post("/auth/register",
                json={"name": email.split("@")[0], "email": email, "password": password})
    return client.post("/auth/login",
                       json={"email": email, "password": password}).json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def me(client, token):
    return client.get("/users/me", headers=auth(token)).json()


def iso(dt: datetime) -> str:
    """Naive UTC ISO string safe to embed in URL query params (no +00:00)."""
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()


def _create_task(client, token, **kwargs):
    body = {"title": "default", **kwargs}
    res = client.post("/tasks", headers=auth(token), json=body)
    assert res.status_code == 201, res.json()
    return res.json()


def _create_proj_task(client, token, project_id, **kwargs):
    body = {"title": "default", **kwargs}
    res = client.post(f"/projects/{project_id}/tasks", headers=auth(token), json=body)
    assert res.status_code == 201, res.json()
    return res.json()


# ─── Shared fixture ───────────────────────────────────────────────────────────

@pytest.fixture
def sort_setup(client):
    """Manager + member, one team, one project."""
    mgr_token = register_and_login(client, "srt_mgr@example.com")
    mem_token  = register_and_login(client, "srt_mem@example.com")
    out_token  = register_and_login(client, "srt_out@example.com")

    team = client.post("/teams", headers=auth(mgr_token),
                       json={"name": "Sort Team"}).json()
    team_id = team["id"]
    client.post(f"/teams/{team_id}/members", headers=auth(mgr_token),
                json={"email": "srt_mem@example.com", "role": "MEMBER"})
    project = client.post(f"/teams/{team_id}/projects", headers=auth(mgr_token),
                          json={"name": "Sort Project"}).json()
    project_id = project["id"]
    mgr_id = me(client, mgr_token)["id"]
    mem_id = me(client, mem_token)["id"]
    return {
        "mgr_token":  mgr_token,
        "mem_token":  mem_token,
        "out_token":  out_token,
        "team_id":    team_id,
        "project_id": project_id,
        "mgr_id":     mgr_id,
        "mem_id":     mem_id,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# INVALID SORT PARAMETERS — 422 from FastAPI
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidSortParams:

    def test_invalid_sort_by_returns_422(self, client):
        token = register_and_login(client, "inv_sb@example.com")
        res = client.get("/tasks?sort_by=password_hash", headers=auth(token))
        assert res.status_code == 422

    def test_invalid_sort_by_arbitrary_column_rejected(self, client):
        token = register_and_login(client, "inv_sb2@example.com")
        res = client.get("/tasks?sort_by=created_by", headers=auth(token))
        assert res.status_code == 422

    def test_invalid_sort_order_returns_422(self, client):
        token = register_and_login(client, "inv_so@example.com")
        res = client.get("/tasks?sort_order=random", headers=auth(token))
        assert res.status_code == 422

    def test_invalid_sort_order_asc_misspelled_rejected(self, client):
        token = register_and_login(client, "inv_so2@example.com")
        res = client.get("/tasks?sort_order=ascending", headers=auth(token))
        assert res.status_code == 422

    def test_invalid_project_sort_by_rejected(self, client, sort_setup):
        mgr = sort_setup["mgr_token"]
        pid = sort_setup["project_id"]
        res = client.get(f"/projects/{pid}/tasks?sort_by=deleted_at", headers=auth(mgr))
        assert res.status_code == 422

    def test_invalid_project_sort_order_rejected(self, client, sort_setup):
        mgr = sort_setup["mgr_token"]
        pid = sort_setup["project_id"]
        res = client.get(f"/projects/{pid}/tasks?sort_order=DESC_PLS", headers=auth(mgr))
        assert res.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# VALID SORT FIELDS — all six allowed fields accepted
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidSortFields:
    """Each valid sort_by field should be accepted (200) for both sort orders."""

    FIELDS = ["created_at", "updated_at", "due_date", "priority", "status", "title"]

    @pytest.mark.parametrize("field", FIELDS)
    def test_sort_by_field_asc_accepted(self, client, field):
        token = register_and_login(client, f"vld_{field}_a@example.com")
        _create_task(client, token, title="T1")
        res = client.get(f"/tasks?sort_by={field}&sort_order=asc", headers=auth(token))
        assert res.status_code == 200

    @pytest.mark.parametrize("field", FIELDS)
    def test_sort_by_field_desc_accepted(self, client, field):
        token = register_and_login(client, f"vld_{field}_d@example.com")
        _create_task(client, token, title="T1")
        res = client.get(f"/tasks?sort_by={field}&sort_order=desc", headers=auth(token))
        assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT SORT ORDER
# ═══════════════════════════════════════════════════════════════════════════════

class TestDefaultSortOrder:

    def test_default_sort_is_created_at_desc(self, client):
        """Without sort params the newest task must appear first."""
        token = register_and_login(client, "def_sort@example.com")
        # Create tasks with a small sleep so created_at actually differs in
        # the test database (SQLite stores with microsecond precision).
        t1 = _create_task(client, token, title="First created")
        time.sleep(0.01)
        t2 = _create_task(client, token, title="Second created")

        d = client.get("/tasks", headers=auth(token)).json()
        ids = [t["id"] for t in d["items"]]
        # Most recently created should be first (desc default)
        assert ids.index(t2["id"]) < ids.index(t1["id"])

    def test_default_parameters_accepted(self, client):
        """No sort params → 200 response."""
        token = register_and_login(client, "def_sort2@example.com")
        res = client.get("/tasks", headers=auth(token))
        assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# SORT BY TITLE
# ═══════════════════════════════════════════════════════════════════════════════

class TestSortByTitle:

    def test_sort_title_asc(self, client):
        token = register_and_login(client, "srt_title_a@example.com")
        _create_task(client, token, title="Zebra")
        _create_task(client, token, title="Apple")
        _create_task(client, token, title="Mango")
        d = client.get("/tasks?sort_by=title&sort_order=asc", headers=auth(token)).json()
        titles = [t["title"] for t in d["items"]]
        assert titles == sorted(titles)

    def test_sort_title_desc(self, client):
        token = register_and_login(client, "srt_title_d@example.com")
        _create_task(client, token, title="Alpha")
        _create_task(client, token, title="Gamma")
        _create_task(client, token, title="Beta")
        d = client.get("/tasks?sort_by=title&sort_order=desc", headers=auth(token)).json()
        titles = [t["title"] for t in d["items"]]
        assert titles == sorted(titles, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SORT BY STATUS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSortByStatus:

    def test_sort_status_asc(self, client):
        token = register_and_login(client, "srt_st_a@example.com")
        t1_id = _create_task(client, token, title="T1")["id"]
        t2_id = _create_task(client, token, title="T2")["id"]
        t3_id = _create_task(client, token, title="T3")["id"]
        client.patch(f"/tasks/{t1_id}", headers=auth(token), json={"status": "COMPLETED"})
        client.patch(f"/tasks/{t2_id}", headers=auth(token), json={"status": "IN_PROGRESS"})
        # T3 remains TODO

        d = client.get("/tasks?sort_by=status&sort_order=asc", headers=auth(token)).json()
        statuses = [t["status"] for t in d["items"]]
        assert statuses == sorted(statuses)

    def test_sort_status_desc(self, client):
        token = register_and_login(client, "srt_st_d@example.com")
        t1_id = _create_task(client, token, title="T1")["id"]
        t2_id = _create_task(client, token, title="T2")["id"]
        t3_id = _create_task(client, token, title="T3")["id"]
        client.patch(f"/tasks/{t1_id}", headers=auth(token), json={"status": "COMPLETED"})
        client.patch(f"/tasks/{t2_id}", headers=auth(token), json={"status": "IN_PROGRESS"})

        d = client.get("/tasks?sort_by=status&sort_order=desc", headers=auth(token)).json()
        statuses = [t["status"] for t in d["items"]]
        assert statuses == sorted(statuses, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SORT BY PRIORITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestSortByPriority:

    def test_sort_priority_asc(self, client):
        token = register_and_login(client, "srt_pri_a@example.com")
        _create_task(client, token, title="H", priority="HIGH")
        _create_task(client, token, title="L", priority="LOW")
        _create_task(client, token, title="M", priority="MEDIUM")
        d = client.get("/tasks?sort_by=priority&sort_order=asc", headers=auth(token)).json()
        priorities = [t["priority"] for t in d["items"]]
        assert priorities == sorted(priorities)

    def test_sort_priority_desc(self, client):
        token = register_and_login(client, "srt_pri_d@example.com")
        _create_task(client, token, title="H", priority="HIGH")
        _create_task(client, token, title="L", priority="LOW")
        _create_task(client, token, title="M", priority="MEDIUM")
        d = client.get("/tasks?sort_by=priority&sort_order=desc", headers=auth(token)).json()
        priorities = [t["priority"] for t in d["items"]]
        assert priorities == sorted(priorities, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SORT BY CREATED_AT
# ═══════════════════════════════════════════════════════════════════════════════

class TestSortByCreatedAt:

    def test_sort_created_at_desc(self, client):
        """Newest first (the default)."""
        token = register_and_login(client, "srt_ca_d@example.com")
        t1 = _create_task(client, token, title="First")
        time.sleep(0.01)
        t2 = _create_task(client, token, title="Second")
        d = client.get("/tasks?sort_by=created_at&sort_order=desc", headers=auth(token)).json()
        ids = [t["id"] for t in d["items"]]
        assert ids.index(t2["id"]) < ids.index(t1["id"])

    def test_sort_created_at_asc(self, client):
        """Oldest first."""
        token = register_and_login(client, "srt_ca_a@example.com")
        t1 = _create_task(client, token, title="First")
        time.sleep(0.01)
        t2 = _create_task(client, token, title="Second")
        d = client.get("/tasks?sort_by=created_at&sort_order=asc", headers=auth(token)).json()
        ids = [t["id"] for t in d["items"]]
        assert ids.index(t1["id"]) < ids.index(t2["id"])


# ═══════════════════════════════════════════════════════════════════════════════
# SORT BY DUE_DATE (including NULL handling)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSortByDueDate:

    def _dt(self, days_offset: int) -> str:
        return iso(datetime.utcnow() + timedelta(days=days_offset))

    def test_sort_due_date_asc_earliest_first(self, client):
        token = register_and_login(client, "srt_dd_a@example.com")
        _create_task(client, token, title="Far",    due_date=self._dt(10))
        _create_task(client, token, title="Near",   due_date=self._dt(2))
        _create_task(client, token, title="Middle", due_date=self._dt(5))

        d = client.get("/tasks?sort_by=due_date&sort_order=asc", headers=auth(token)).json()
        titles = [t["title"] for t in d["items"] if t["due_date"] is not None]
        assert titles == ["Near", "Middle", "Far"]

    def test_sort_due_date_desc_latest_first(self, client):
        token = register_and_login(client, "srt_dd_d@example.com")
        _create_task(client, token, title="Far",    due_date=self._dt(10))
        _create_task(client, token, title="Near",   due_date=self._dt(2))
        _create_task(client, token, title="Middle", due_date=self._dt(5))

        d = client.get("/tasks?sort_by=due_date&sort_order=desc", headers=auth(token)).json()
        titles = [t["title"] for t in d["items"] if t["due_date"] is not None]
        assert titles == ["Far", "Middle", "Near"]

    def test_null_due_dates_appear_in_results(self, client):
        """Tasks with no due_date are still returned when sorting by due_date."""
        token = register_and_login(client, "srt_dd_null@example.com")
        _create_task(client, token, title="Has date", due_date=self._dt(3))
        _create_task(client, token, title="No date")  # due_date = None

        d = client.get("/tasks?sort_by=due_date&sort_order=asc", headers=auth(token)).json()
        assert d["total"] == 2
        titles = [t["title"] for t in d["items"]]
        assert "Has date" in titles
        assert "No date" in titles

    def test_null_due_dates_sort_consistently(self, client):
        """NULL due dates must always appear at a consistent position (not random)."""
        token = register_and_login(client, "srt_dd_null2@example.com")
        _create_task(client, token, title="D1")
        _create_task(client, token, title="D2")

        asc1  = client.get("/tasks?sort_by=due_date&sort_order=asc",  headers=auth(token)).json()
        asc2  = client.get("/tasks?sort_by=due_date&sort_order=asc",  headers=auth(token)).json()
        desc1 = client.get("/tasks?sort_by=due_date&sort_order=desc", headers=auth(token)).json()
        desc2 = client.get("/tasks?sort_by=due_date&sort_order=desc", headers=auth(token)).json()

        # Same query must return same order every time
        assert [t["id"] for t in asc1["items"]] == [t["id"] for t in asc2["items"]]
        assert [t["id"] for t in desc1["items"]] == [t["id"] for t in desc2["items"]]


# ═══════════════════════════════════════════════════════════════════════════════
# TIE-BREAKING DETERMINISM
# ═══════════════════════════════════════════════════════════════════════════════

class TestTieBreaking:

    def test_same_title_order_is_deterministic(self, client):
        """Multiple tasks with the same title must return in consistent order."""
        token = register_and_login(client, "tie_title@example.com")
        for _ in range(4):
            _create_task(client, token, title="Duplicate")

        r1 = client.get("/tasks?sort_by=title&sort_order=asc", headers=auth(token)).json()
        r2 = client.get("/tasks?sort_by=title&sort_order=asc", headers=auth(token)).json()
        assert [t["id"] for t in r1["items"]] == [t["id"] for t in r2["items"]]

    def test_same_priority_order_is_deterministic(self, client):
        token = register_and_login(client, "tie_pri@example.com")
        for i in range(4):
            _create_task(client, token, title=f"High-{i}", priority="HIGH")

        r1 = client.get("/tasks?sort_by=priority&sort_order=desc", headers=auth(token)).json()
        r2 = client.get("/tasks?sort_by=priority&sort_order=desc", headers=auth(token)).json()
        assert [t["id"] for t in r1["items"]] == [t["id"] for t in r2["items"]]

    def test_pagination_across_pages_no_duplicate_with_tiebreak(self, client):
        """With tie-breaking, page 1 and page 2 must not share records."""
        token = register_and_login(client, "tie_pg@example.com")
        for i in range(6):
            _create_task(client, token, title="Same title")

        p1 = client.get("/tasks?sort_by=title&sort_order=asc&page=1&page_size=3", headers=auth(token)).json()
        p2 = client.get("/tasks?sort_by=title&sort_order=asc&page=2&page_size=3", headers=auth(token)).json()

        ids_p1 = {t["id"] for t in p1["items"]}
        ids_p2 = {t["id"] for t in p2["items"]}
        assert len(ids_p1) == 3
        assert len(ids_p2) == 3
        assert ids_p1.isdisjoint(ids_p2), "Pages must not share records"


# ═══════════════════════════════════════════════════════════════════════════════
# SORTING + PHASE 7A FILTERS COMBINED
# ═══════════════════════════════════════════════════════════════════════════════

class TestSortWithFilters:

    def test_sort_with_status_filter(self, client):
        token = register_and_login(client, "sf_combo@example.com")
        _create_task(client, token, title="Todo Zebra")
        _create_task(client, token, title="Todo Apple")
        wip_id = _create_task(client, token, title="WIP task")["id"]
        client.patch(f"/tasks/{wip_id}", headers=auth(token), json={"status": "IN_PROGRESS"})

        d = client.get("/tasks?status=TODO&sort_by=title&sort_order=asc", headers=auth(token)).json()
        titles = [t["title"] for t in d["items"]]
        assert "WIP task" not in titles
        assert titles == sorted(titles)

    def test_sort_with_priority_filter(self, client):
        token = register_and_login(client, "pf_sort@example.com")
        _create_task(client, token, title="High Zebra", priority="HIGH")
        _create_task(client, token, title="High Apple", priority="HIGH")
        _create_task(client, token, title="Low task",   priority="LOW")

        d = client.get("/tasks?priority=HIGH&sort_by=title&sort_order=asc", headers=auth(token)).json()
        assert d["total"] == 2
        titles = [t["title"] for t in d["items"]]
        assert titles == sorted(titles)
        assert all(t["priority"] == "HIGH" for t in d["items"])

    def test_sort_with_search(self, client):
        token = register_and_login(client, "ss_sort@example.com")
        _create_task(client, token, title="api deployment")
        _create_task(client, token, title="api review")
        _create_task(client, token, title="database backup")

        d = client.get("/tasks?search=api&sort_by=title&sort_order=asc", headers=auth(token)).json()
        assert d["total"] == 2
        titles = [t["title"] for t in d["items"]]
        assert titles == sorted(titles)
        assert all("api" in t["title"] for t in d["items"])

    def test_sort_with_due_date_filter(self, client):
        token = register_and_login(client, "dd_sort@example.com")
        base = datetime.utcnow()
        _create_task(client, token, title="Soon",  due_date=iso(base + timedelta(days=1)))
        _create_task(client, token, title="Later", due_date=iso(base + timedelta(days=5)))
        _create_task(client, token, title="Past",  due_date=iso(base - timedelta(days=2)))

        cutoff = iso(base)
        d = client.get(f"/tasks?due_after={cutoff}&sort_by=due_date&sort_order=asc",
                       headers=auth(token)).json()
        assert d["total"] == 2
        titles = [t["title"] for t in d["items"]]
        assert titles[0] == "Soon"
        assert titles[1] == "Later"

    def test_sort_with_multiple_filters(self, client):
        token = register_and_login(client, "mf_sort@example.com")
        _create_task(client, token, title="api high todo",    priority="HIGH")
        _create_task(client, token, title="api medium todo",  priority="MEDIUM")
        _create_task(client, token, title="api high wip",     priority="HIGH")

        wip_d = client.get("/tasks?search=api high wip", headers=auth(token)).json()
        if wip_d["items"]:
            client.patch(f"/tasks/{wip_d['items'][0]['id']}", headers=auth(token),
                         json={"status": "IN_PROGRESS"})

        d = client.get("/tasks?search=api&status=TODO&sort_by=title&sort_order=asc",
                       headers=auth(token)).json()
        assert d["total"] == 2
        titles = [t["title"] for t in d["items"]]
        assert titles == sorted(titles)


# ═══════════════════════════════════════════════════════════════════════════════
# SORTING + PAGINATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestSortWithPagination:

    def test_sort_applied_before_pagination(self, client):
        """Page 1 with sort_by=title asc must contain the alphabetically first titles."""
        token = register_and_login(client, "srt_pg_order@example.com")
        titles = ["Elephant", "Apple", "Banana", "Cherry", "Dragon"]
        for t in titles:
            _create_task(client, token, title=t)

        d = client.get("/tasks?sort_by=title&sort_order=asc&page=1&page_size=2",
                       headers=auth(token)).json()
        assert d["total"] == 5
        assert len(d["items"]) == 2
        page_titles = [t["title"] for t in d["items"]]
        # The first page should have the two alphabetically first titles
        assert page_titles == sorted(titles)[:2]

    def test_sort_pagination_page_2(self, client):
        token = register_and_login(client, "srt_pg2@example.com")
        titles = ["Elephant", "Apple", "Banana", "Cherry", "Dragon"]
        for t in titles:
            _create_task(client, token, title=t)

        p1 = client.get("/tasks?sort_by=title&sort_order=asc&page=1&page_size=2",
                        headers=auth(token)).json()
        p2 = client.get("/tasks?sort_by=title&sort_order=asc&page=2&page_size=2",
                        headers=auth(token)).json()
        p3 = client.get("/tasks?sort_by=title&sort_order=asc&page=3&page_size=2",
                        headers=auth(token)).json()

        all_items = p1["items"] + p2["items"] + p3["items"]
        returned_titles = [t["title"] for t in all_items]
        assert returned_titles == sorted(titles)

    def test_sort_desc_pagination_complete_coverage(self, client):
        token = register_and_login(client, "srt_desc_pg@example.com")
        titles = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        for t in titles:
            _create_task(client, token, title=t)

        p1 = client.get("/tasks?sort_by=title&sort_order=desc&page=1&page_size=3",
                        headers=auth(token)).json()
        p2 = client.get("/tasks?sort_by=title&sort_order=desc&page=2&page_size=3",
                        headers=auth(token)).json()

        all_titles = [t["title"] for t in p1["items"] + p2["items"]]
        assert all_titles == sorted(titles, reverse=True)

    def test_total_unchanged_by_sort(self, client):
        """Sorting must not affect the total count."""
        token = register_and_login(client, "srt_total@example.com")
        for i in range(5):
            _create_task(client, token, title=f"Task {i}")

        d_asc  = client.get("/tasks?sort_by=title&sort_order=asc",  headers=auth(token)).json()
        d_desc = client.get("/tasks?sort_by=title&sort_order=desc", headers=auth(token)).json()
        assert d_asc["total"] == d_desc["total"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TASK SORTING
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectTaskSorting:

    def test_project_sort_by_title_asc(self, client, sort_setup):
        mgr = sort_setup["mgr_token"]
        pid = sort_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="Zebra")
        _create_proj_task(client, mgr, pid, title="Apple")
        _create_proj_task(client, mgr, pid, title="Mango")

        d = client.get(f"/projects/{pid}/tasks?sort_by=title&sort_order=asc",
                       headers=auth(mgr)).json()
        titles = [t["title"] for t in d["items"]]
        assert titles == sorted(titles)

    def test_project_sort_by_priority_desc(self, client, sort_setup):
        mgr = sort_setup["mgr_token"]
        pid = sort_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="Low",  priority="LOW")
        _create_proj_task(client, mgr, pid, title="High", priority="HIGH")
        _create_proj_task(client, mgr, pid, title="Med",  priority="MEDIUM")

        d = client.get(f"/projects/{pid}/tasks?sort_by=priority&sort_order=desc",
                       headers=auth(mgr)).json()
        priorities = [t["priority"] for t in d["items"]]
        assert priorities == sorted(priorities, reverse=True)

    def test_project_sort_stays_scoped_to_project(self, client, sort_setup):
        """Sort on project A must not leak tasks from project B."""
        mgr = sort_setup["mgr_token"]
        pid = sort_setup["project_id"]
        team_id = sort_setup["team_id"]

        pid2 = client.post(f"/teams/{team_id}/projects", headers=auth(mgr),
                           json={"name": "Second"}).json()["id"]

        _create_proj_task(client, mgr, pid,  title="Project1 task")
        _create_proj_task(client, mgr, pid2, title="Project2 task")

        d = client.get(f"/projects/{pid}/tasks?sort_by=title&sort_order=asc",
                       headers=auth(mgr)).json()
        assert d["total"] == 1
        assert d["items"][0]["project_id"] == pid

    def test_project_sort_with_filter_and_pagination(self, client, sort_setup):
        mgr = sort_setup["mgr_token"]
        pid = sort_setup["project_id"]
        for i in range(5):
            _create_proj_task(client, mgr, pid, title=f"High task {i}", priority="HIGH")
        _create_proj_task(client, mgr, pid, title="Low task", priority="LOW")

        d = client.get(
            f"/projects/{pid}/tasks?priority=HIGH&sort_by=title&sort_order=asc&page=1&page_size=3",
            headers=auth(mgr),
        ).json()
        assert d["total"] == 5
        assert d["total_pages"] == 2
        assert len(d["items"]) == 3
        titles = [t["title"] for t in d["items"]]
        assert titles == sorted(titles)

    def test_project_member_can_sort(self, client, sort_setup):
        mgr = sort_setup["mgr_token"]
        mem = sort_setup["mem_token"]
        pid = sort_setup["project_id"]
        _create_proj_task(client, mgr, pid, title="Zebra")
        _create_proj_task(client, mgr, pid, title="Apple")

        res = client.get(f"/projects/{pid}/tasks?sort_by=title&sort_order=asc",
                         headers=auth(mem))
        assert res.status_code == 200

    def test_project_sort_by_due_date_asc(self, client, sort_setup):
        mgr = sort_setup["mgr_token"]
        pid = sort_setup["project_id"]
        base = datetime.utcnow()
        _create_proj_task(client, mgr, pid, title="Far",  due_date=iso(base + timedelta(days=10)))
        _create_proj_task(client, mgr, pid, title="Near", due_date=iso(base + timedelta(days=2)))

        d = client.get(f"/projects/{pid}/tasks?sort_by=due_date&sort_order=asc",
                       headers=auth(mgr)).json()
        titles = [t["title"] for t in d["items"] if t["due_date"] is not None]
        assert titles[0] == "Near"
        assert titles[-1] == "Far"


# ═══════════════════════════════════════════════════════════════════════════════
# AUTHORIZATION PRESERVED DURING SORTING
# ═══════════════════════════════════════════════════════════════════════════════

class TestSortingAuthorization:

    def test_sort_does_not_expose_other_users_tasks(self, client):
        t1 = register_and_login(client, "srt_auth_a@example.com")
        t2 = register_and_login(client, "srt_auth_b@example.com")
        for title in ["Alpha", "Beta", "Gamma"]:
            _create_task(client, t1, title=title)
        _create_task(client, t2, title="My own task")

        d = client.get("/tasks?sort_by=title&sort_order=asc", headers=auth(t2)).json()
        assert d["total"] == 1
        assert d["items"][0]["title"] == "My own task"

    def test_non_member_cannot_sort_project_tasks(self, client, sort_setup):
        out = sort_setup["out_token"]
        pid = sort_setup["project_id"]
        res = client.get(f"/projects/{pid}/tasks?sort_by=title&sort_order=asc",
                         headers=auth(out))
        assert res.status_code == 403

    def test_sort_total_reflects_only_authorized_tasks(self, client):
        t1 = register_and_login(client, "srt_total_a@example.com")
        t2 = register_and_login(client, "srt_total_b@example.com")
        for i in range(5):
            _create_task(client, t1, title=f"T1 task {i}")
        _create_task(client, t2, title="My task")

        d = client.get("/tasks?sort_by=title&sort_order=asc", headers=auth(t2)).json()
        assert d["total"] == 1

    def test_pagination_with_sort_does_not_leak(self, client):
        """Page 2 for a user with 1 task must be empty regardless of sort."""
        t1 = register_and_login(client, "srt_leak_a@example.com")
        t2 = register_and_login(client, "srt_leak_b@example.com")
        _create_task(client, t1, title="Only task")
        for i in range(10):
            _create_task(client, t2, title=f"Noise {i}")

        d = client.get("/tasks?sort_by=title&sort_order=asc&page=2&page_size=1",
                       headers=auth(t1)).json()
        assert d["items"] == []
        assert d["total"] == 1

    def test_sort_with_filter_does_not_bypass_authorization(self, client):
        t1 = register_and_login(client, "srt_bypass_a@example.com")
        t2 = register_and_login(client, "srt_bypass_b@example.com")
        _create_task(client, t1, title="Secret high priority", priority="HIGH")
        _create_task(client, t2, title="My medium task", priority="MEDIUM")

        # t2 filters by HIGH priority with sort — must not see t1's task
        d = client.get("/tasks?priority=HIGH&sort_by=title&sort_order=asc",
                       headers=auth(t2)).json()
        assert d["total"] == 0
