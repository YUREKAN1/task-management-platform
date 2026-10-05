import pytest
from uuid import uuid4

def get_token(client, email, password="pass"):
    client.post("/auth/register", json={"name": email.split('@')[0], "email": email, "password": password})
    return client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]


@pytest.fixture
def setup_users(client):
    manager_token = get_token(client, "proj_mgr@example.com")
    member_token = get_token(client, "proj_mem@example.com")
    outsider_token = get_token(client, "proj_out@example.com")

    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Project Team"}).json()
    team_id = team["id"]

    client.post(f"/teams/{team_id}/members", headers={"Authorization": f"Bearer {manager_token}"}, json={"email": "proj_mem@example.com", "role": "MEMBER"})

    return {
        "manager_token": manager_token,
        "member_token": member_token,
        "outsider_token": outsider_token,
        "team_id": team_id,
    }


# ─── CREATE ──────────────────────────────────────────────────────────────────

def test_create_project_manager(client, setup_users):
    manager_token = setup_users["manager_token"]
    team_id = setup_users["team_id"]

    res = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Alpha Project"})
    assert res.status_code == 201
    assert res.json()["name"] == "Alpha Project"
    assert res.json()["team_id"] == team_id


def test_create_project_unauthenticated(client, setup_users):
    team_id = setup_users["team_id"]
    res = client.post(f"/teams/{team_id}/projects", json={"name": "No Auth Project"})
    assert res.status_code == 401


def test_create_project_member_forbidden(client, setup_users):
    res = client.post(
        f"/teams/{setup_users['team_id']}/projects",
        headers={"Authorization": f"Bearer {setup_users['member_token']}"},
        json={"name": "Beta Project"},
    )
    assert res.status_code == 403


def test_create_project_outsider_forbidden(client, setup_users):
    res = client.post(
        f"/teams/{setup_users['team_id']}/projects",
        headers={"Authorization": f"Bearer {setup_users['outsider_token']}"},
        json={"name": "Gamma Project"},
    )
    assert res.status_code == 403


def test_create_project_nonexistent_team(client, setup_users):
    manager_token = setup_users["manager_token"]
    res = client.post(f"/teams/{uuid4()}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Delta Project"})
    assert res.status_code == 404


def test_create_project_created_by_from_auth(client, setup_users):
    """created_by must come from the authenticated user, not client-provided JSON."""
    manager_token = setup_users["manager_token"]
    team_id = setup_users["team_id"]
    # Extra keys like created_by / team_id in body are ignored by ProjectCreate
    res = client.post(
        f"/teams/{team_id}/projects",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"name": "No Spoof", "created_by": str(uuid4()), "team_id": str(uuid4())},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["team_id"] == team_id  # URL team_id wins
    assert "password_hash" not in data


# ─── LIST ────────────────────────────────────────────────────────────────────

def test_list_team_projects_manager(client, setup_users):
    manager_token = setup_users["manager_token"]
    team_id = setup_users["team_id"]
    client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj 1"})

    res = client.get(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"})
    assert res.status_code == 200
    assert len(res.json()) >= 1


def test_list_team_projects_member(client, setup_users):
    manager_token = setup_users["manager_token"]
    member_token = setup_users["member_token"]
    team_id = setup_users["team_id"]
    client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj 2"})

    res = client.get(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {member_token}"})
    assert res.status_code == 200
    assert len(res.json()) >= 1


def test_list_team_projects_outsider_forbidden(client, setup_users):
    outsider_token = setup_users["outsider_token"]
    team_id = setup_users["team_id"]
    res = client.get(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {outsider_token}"})
    assert res.status_code == 403


def test_list_nonexistent_team_projects(client, setup_users):
    manager_token = setup_users["manager_token"]
    res = client.get(f"/teams/{uuid4()}/projects", headers={"Authorization": f"Bearer {manager_token}"})
    assert res.status_code == 404


def test_unrelated_team_projects_not_returned(client, setup_users):
    """Team A member must never see Team B projects."""
    manager_token = setup_users["manager_token"]
    team_a_id = setup_users["team_id"]

    team_b = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Team B Isolation"}).json()
    team_b_id = team_b["id"]

    client.post(f"/teams/{team_b_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Team B Project"})
    client.post(f"/teams/{team_a_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Team A Project"})

    a_names = [p["name"] for p in client.get(f"/teams/{team_a_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}).json()]
    assert "Team B Project" not in a_names
    assert "Team A Project" in a_names

    b_names = [p["name"] for p in client.get(f"/teams/{team_b_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}).json()]
    assert "Team A Project" not in b_names
    assert "Team B Project" in b_names


# ─── GET DETAIL ──────────────────────────────────────────────────────────────

def test_get_project_member(client, setup_users):
    manager_token = setup_users["manager_token"]
    member_token = setup_users["member_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj Detail"}).json()

    assert client.get(f"/projects/{proj['id']}", headers={"Authorization": f"Bearer {manager_token}"}).status_code == 200
    assert client.get(f"/projects/{proj['id']}", headers={"Authorization": f"Bearer {member_token}"}).status_code == 200


def test_get_project_non_member_forbidden(client, setup_users):
    manager_token = setup_users["manager_token"]
    outsider_token = setup_users["outsider_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj Hidden"}).json()

    assert client.get(f"/projects/{proj['id']}", headers={"Authorization": f"Bearer {outsider_token}"}).status_code == 403


def test_get_project_nonexistent(client, setup_users):
    manager_token = setup_users["manager_token"]
    assert client.get(f"/projects/{uuid4()}", headers={"Authorization": f"Bearer {manager_token}"}).status_code == 404


# ─── UPDATE ──────────────────────────────────────────────────────────────────

def test_update_project_manager(client, setup_users):
    manager_token = setup_users["manager_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj Update"}).json()

    res = client.patch(f"/projects/{proj['id']}", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Updated Name"})
    assert res.status_code == 200
    assert res.json()["name"] == "Updated Name"


def test_update_project_member_forbidden(client, setup_users):
    manager_token = setup_users["manager_token"]
    member_token = setup_users["member_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj NoMember"}).json()

    assert client.patch(f"/projects/{proj['id']}", headers={"Authorization": f"Bearer {member_token}"}, json={"name": "Hacked"}).status_code == 403


def test_update_project_outsider_forbidden(client, setup_users):
    manager_token = setup_users["manager_token"]
    outsider_token = setup_users["outsider_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj NoOuter"}).json()

    assert client.patch(f"/projects/{proj['id']}", headers={"Authorization": f"Bearer {outsider_token}"}, json={"name": "Hacked"}).status_code == 403


def test_update_project_nonexistent(client, setup_users):
    manager_token = setup_users["manager_token"]
    assert client.patch(f"/projects/{uuid4()}", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Ghost"}).status_code == 404


def test_update_project_cannot_change_protected_fields(client, setup_users):
    """team_id and created_by must not change even if passed in the body."""
    manager_token = setup_users["manager_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Protected"}).json()

    res = client.patch(
        f"/projects/{proj['id']}",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"name": "Safe Name", "team_id": str(uuid4()), "created_by": str(uuid4())},
    )
    assert res.status_code == 200
    assert res.json()["team_id"] == team_id  # unchanged
    assert res.json()["created_by"] == proj["created_by"]  # unchanged


# ─── DELETE ──────────────────────────────────────────────────────────────────

def test_delete_project_with_confirm(client, setup_users):
    manager_token = setup_users["manager_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj Delete"}).json()
    proj_id = proj["id"]

    assert client.delete(f"/projects/{proj_id}?confirm=true", headers={"Authorization": f"Bearer {manager_token}"}).status_code == 204
    assert client.get(f"/projects/{proj_id}", headers={"Authorization": f"Bearer {manager_token}"}).status_code == 404


def test_delete_project_without_confirm_fails(client, setup_users):
    manager_token = setup_users["manager_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj Keep"}).json()

    assert client.delete(f"/projects/{proj['id']}", headers={"Authorization": f"Bearer {manager_token}"}).status_code == 400
    # Still exists
    assert client.get(f"/projects/{proj['id']}", headers={"Authorization": f"Bearer {manager_token}"}).status_code == 200


def test_delete_project_member_forbidden(client, setup_users):
    manager_token = setup_users["manager_token"]
    member_token = setup_users["member_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj MemberDel"}).json()

    assert client.delete(f"/projects/{proj['id']}?confirm=true", headers={"Authorization": f"Bearer {member_token}"}).status_code == 403


def test_delete_project_outsider_forbidden(client, setup_users):
    manager_token = setup_users["manager_token"]
    outsider_token = setup_users["outsider_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Proj OutDel"}).json()

    assert client.delete(f"/projects/{proj['id']}?confirm=true", headers={"Authorization": f"Bearer {outsider_token}"}).status_code == 403


def test_delete_project_nonexistent(client, setup_users):
    manager_token = setup_users["manager_token"]
    assert client.delete(f"/projects/{uuid4()}?confirm=true", headers={"Authorization": f"Bearer {manager_token}"}).status_code == 404


# ─── SECURITY ────────────────────────────────────────────────────────────────

def test_project_response_no_sensitive_fields(client, setup_users):
    manager_token = setup_users["manager_token"]
    team_id = setup_users["team_id"]

    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Security Check"}).json()
    assert "password_hash" not in proj
    assert "password" not in proj

    detail = client.get(f"/projects/{proj['id']}", headers={"Authorization": f"Bearer {manager_token}"}).json()
    assert "password_hash" not in detail


def test_outsider_cannot_access_project_via_uuid(client, setup_users):
    """Knowing the project UUID must NOT bypass team membership check."""
    manager_token = setup_users["manager_token"]
    outsider_token = setup_users["outsider_token"]
    team_id = setup_users["team_id"]
    proj = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Secret Project"}).json()
    proj_id = proj["id"]

    assert client.get(f"/projects/{proj_id}", headers={"Authorization": f"Bearer {outsider_token}"}).status_code == 403
    assert client.patch(f"/projects/{proj_id}", headers={"Authorization": f"Bearer {outsider_token}"}, json={"name": "Hacked"}).status_code == 403
    assert client.delete(f"/projects/{proj_id}?confirm=true", headers={"Authorization": f"Bearer {outsider_token}"}).status_code == 403


# ─── GLOBAL ADMIN ────────────────────────────────────────────────────────────

def test_global_admin_bypass(client, setup_users, db_session):
    from app.models.user import User
    from app.models.enums import GlobalRole

    admin_token = get_token(client, "admin@example.com")
    admin_user = db_session.query(User).filter(User.email == "admin@example.com").first()
    admin_user.global_role = GlobalRole.ADMIN
    db_session.commit()

    team_id = setup_users["team_id"]

    # Admin (not a team member) creates project
    res = client.post(f"/teams/{team_id}/projects", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "Admin Proj"})
    assert res.status_code == 201
    proj_id = res.json()["id"]

    assert client.get(f"/projects/{proj_id}", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200
    assert client.delete(f"/projects/{proj_id}?confirm=true", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 204
