import pytest
from app.models.user import User

def test_get_users_me_success(client):
    res = client.post("/auth/register", json={"name": "U1", "email": "u1@example.com", "password": "pass"})
    token_res = client.post("/auth/login", json={"email": "u1@example.com", "password": "pass"})
    token = token_res.json()["access_token"]
    
    me_res = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "u1@example.com"
    assert "password_hash" not in me_res.json()

def test_get_users_me_unauthenticated(client):
    res = client.get("/users/me")
    assert res.status_code == 401

def test_update_users_me(client):
    client.post("/auth/register", json={"name": "U2", "email": "u2@example.com", "password": "pass"})
    token = client.post("/auth/login", json={"email": "u2@example.com", "password": "pass"}).json()["access_token"]
    
    res = client.patch("/users/me", headers={"Authorization": f"Bearer {token}"}, json={"name": "U2 Updated"})
    assert res.status_code == 200
    assert res.json()["name"] == "U2 Updated"

def test_update_users_me_email_normalization(client):
    client.post("/auth/register", json={"name": "U3", "email": "u3@example.com", "password": "pass"})
    token = client.post("/auth/login", json={"email": "u3@example.com", "password": "pass"}).json()["access_token"]
    
    res = client.patch("/users/me", headers={"Authorization": f"Bearer {token}"}, json={"email": " U3-new@EXAMPLE.COM "})
    assert res.status_code == 200
    assert res.json()["email"] == "u3-new@example.com"

def test_update_users_me_duplicate_email(client):
    client.post("/auth/register", json={"name": "U4", "email": "u4@example.com", "password": "pass"})
    client.post("/auth/register", json={"name": "U5", "email": "u5@example.com", "password": "pass"})
    token = client.post("/auth/login", json={"email": "u5@example.com", "password": "pass"}).json()["access_token"]
    
    res = client.patch("/users/me", headers={"Authorization": f"Bearer {token}"}, json={"email": "u4@example.com"})
    assert res.status_code == 409
