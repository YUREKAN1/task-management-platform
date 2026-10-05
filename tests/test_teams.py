import pytest
from app.models.enums import TeamRole

def get_token(client, email, password="pass"):
    client.post("/auth/register", json={"name": email.split('@')[0], "email": email, "password": password})
    return client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]

def test_create_team(client):
    token = get_token(client, "team1@example.com")
    res = client.post("/teams", headers={"Authorization": f"Bearer {token}"}, json={"name": "Alpha Team"})
    assert res.status_code == 201
    assert res.json()["name"] == "Alpha Team"

def test_list_teams(client):
    token = get_token(client, "team2@example.com")
    client.post("/teams", headers={"Authorization": f"Bearer {token}"}, json={"name": "Beta Team"})
    
    res = client.get("/teams", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["user_role"] == "MANAGER"

def test_team_detail_member(client):
    token = get_token(client, "team3@example.com")
    team = client.post("/teams", headers={"Authorization": f"Bearer {token}"}, json={"name": "Gamma Team"}).json()
    
    res = client.get(f"/teams/{team['id']}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

def test_team_detail_non_member(client):
    token1 = get_token(client, "team4a@example.com")
    token2 = get_token(client, "team4b@example.com")
    team = client.post("/teams", headers={"Authorization": f"Bearer {token1}"}, json={"name": "Delta Team"}).json()
    
    res = client.get(f"/teams/{team['id']}", headers={"Authorization": f"Bearer {token2}"})
    assert res.status_code == 403

def test_add_member_manager(client):
    manager_token = get_token(client, "team5mgr@example.com")
    get_token(client, "team5usr@example.com") # register target user
    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Epsilon Team"}).json()
    
    res = client.post(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {manager_token}"}, json={"email": "team5usr@example.com", "role": "MEMBER"})
    assert res.status_code == 201
    assert res.json()["role"] == "MEMBER"

def test_add_member_normal_member_forbidden(client):
    manager_token = get_token(client, "team6mgr@example.com")
    member_token = get_token(client, "team6mem@example.com")
    get_token(client, "team6trg@example.com") # register target user
    
    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Zeta Team"}).json()
    client.post(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {manager_token}"}, json={"email": "team6mem@example.com", "role": "MEMBER"})
    
    # Normal member tries to add
    res = client.post(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {member_token}"}, json={"email": "team6trg@example.com", "role": "MEMBER"})
    assert res.status_code == 403

def test_remove_member_prevent_last_manager(client):
    manager_token = get_token(client, "team7mgr@example.com")
    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Eta Team"}).json()
    mgr_id = client.get("/users/me", headers={"Authorization": f"Bearer {manager_token}"}).json()["id"]
    
    res = client.delete(f"/teams/{team['id']}/members/{mgr_id}", headers={"Authorization": f"Bearer {manager_token}"})
    assert res.status_code == 400

def test_update_member_prevent_last_manager(client):
    manager_token = get_token(client, "team8mgr@example.com")
    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Theta Team"}).json()
    mgr_id = client.get("/users/me", headers={"Authorization": f"Bearer {manager_token}"}).json()["id"]
    
    res = client.patch(f"/teams/{team['id']}/members/{mgr_id}", headers={"Authorization": f"Bearer {manager_token}"}, json={"role": "MEMBER"})
    assert res.status_code == 400

def test_update_member_role(client):
    manager_token = get_token(client, "team9mgr@example.com")
    get_token(client, "team9usr@example.com")
    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Iota Team"}).json()
    
    mem_res = client.post(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {manager_token}"}, json={"email": "team9usr@example.com", "role": "MEMBER"}).json()
    
    # Promote to MANAGER
    res = client.patch(f"/teams/{team['id']}/members/{mem_res['user_id']}", headers={"Authorization": f"Bearer {manager_token}"}, json={"role": "MANAGER"})
    assert res.status_code == 200
    assert res.json()["role"] == "MANAGER"

from uuid import uuid4

def test_get_team_nonexistent(client):
    token = get_token(client, "team10mgr@example.com")
    res = client.get(f"/teams/{uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404

def test_remove_team_member_success(client):
    manager_token = get_token(client, "team11mgr@example.com")
    member_token = get_token(client, "team11mem@example.com")
    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Kappa Team"}).json()
    
    mem_res = client.post(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {manager_token}"}, json={"email": "team11mem@example.com", "role": "MEMBER"}).json()
    
    # Manager removes member
    del_res = client.delete(f"/teams/{team['id']}/members/{mem_res['user_id']}", headers={"Authorization": f"Bearer {manager_token}"})
    assert del_res.status_code == 204
    
    # Removed member can no longer view team
    check_res = client.get(f"/teams/{team['id']}", headers={"Authorization": f"Bearer {member_token}"})
    assert check_res.status_code == 403

def test_add_duplicate_member_conflict(client):
    manager_token = get_token(client, "team12mgr@example.com")
    get_token(client, "team12usr@example.com")
    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Lambda Team"}).json()
    
    # Add member first time
    res1 = client.post(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {manager_token}"}, json={"email": "team12usr@example.com", "role": "MEMBER"})
    assert res1.status_code == 201
    
    # Try adding again -> 409 Conflict
    res2 = client.post(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {manager_token}"}, json={"email": "team12usr@example.com", "role": "MEMBER"})
    assert res2.status_code == 409
    assert "already a member" in res2.json()["detail"]

def test_get_team_members(client):
    manager_token = get_token(client, "team13mgr@example.com")
    member_token = get_token(client, "team13mem@example.com")
    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Mu Team"}).json()
    client.post(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {manager_token}"}, json={"email": "team13mem@example.com", "role": "MEMBER"})
    
    # Team member lists members
    res = client.get(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {member_token}"})
    assert res.status_code == 200
    members = res.json()
    assert len(members) == 2
    emails = {m["email"] for m in members}
    assert "team13mgr@example.com" in emails
    assert "team13mem@example.com" in emails

def test_get_team_members_non_member_forbidden(client):
    manager_token = get_token(client, "team14mgr@example.com")
    outsider_token = get_token(client, "team14out@example.com")
    team = client.post("/teams", headers={"Authorization": f"Bearer {manager_token}"}, json={"name": "Nu Team"}).json()
    
    res = client.get(f"/teams/{team['id']}/members", headers={"Authorization": f"Bearer {outsider_token}"})
    assert res.status_code == 403

def test_teams_unauthenticated_requests(client):
    res_list = client.get("/teams")
    assert res_list.status_code == 401
    res_create = client.post("/teams", json={"name": "No Auth"})
    assert res_create.status_code == 401
