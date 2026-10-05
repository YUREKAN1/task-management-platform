import pytest
from app.models.user import User
import time
from app.core.security import create_access_token

def test_register_user_success(client):
    response = client.post("/auth/register", json={"name": "Alice", "email": "alice@example.com", "password": "password123"})
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["name"] == "Alice"
    assert "password_hash" not in data
    assert "password" not in data
    assert data["global_role"] == "USER"
    assert data["is_active"] == True

def test_register_email_normalization(client, db_session):
    response = client.post("/auth/register", json={"name": "Bob", "email": "  BoB@ExAmPlE.com  ", "password": "password123"})
    assert response.status_code == 201
    assert response.json()["email"] == "bob@example.com"
    
    # Verify in db
    user = db_session.query(User).filter(User.email == "bob@example.com").first()
    assert user is not None
    assert user.password_hash != "password123" # Hashed!

def test_duplicate_email_different_casing(client):
    client.post("/auth/register", json={"name": "Charlie", "email": "charlie@example.com", "password": "pass"})
    response = client.post("/auth/register", json={"name": "Charlie2", "email": " CHARLIE@EXAMPLE.COM ", "password": "pass"})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

def test_login_success(client):
    client.post("/auth/register", json={"name": "Dave", "email": "dave@example.com", "password": "password123"})
    response = client.post("/auth/login", json={"email": "DAVE@example.com", "password": "password123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_wrong_password(client):
    client.post("/auth/register", json={"name": "Eve", "email": "eve@example.com", "password": "password123"})
    response = client.post("/auth/login", json={"email": "eve@example.com", "password": "wrong"})
    assert response.status_code == 401

def test_login_nonexistent_user(client):
    response = client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert response.status_code == 401

def test_auth_me(client):
    client.post("/auth/register", json={"name": "Frank", "email": "frank@example.com", "password": "password123"})
    login_res = client.post("/auth/login", json={"email": "frank@example.com", "password": "password123"})
    token = login_res.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "frank@example.com"
    assert "password_hash" not in data

def test_missing_bearer_token(client):
    response = client.get("/auth/me")
    assert response.status_code == 401

def test_malformed_jwt(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer badtoken123"})
    assert response.status_code == 401

def test_expired_jwt(client, monkeypatch):
    import app.core.config
    monkeypatch.setattr(app.core.config.settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 0)
    token = create_access_token("test-sub-123")
    # Small sleep just in case
    time.sleep(0.1)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401

def test_inactive_user(client, db_session):
    res = client.post("/auth/register", json={"name": "Grace", "email": "grace@example.com", "password": "password123"})
    import uuid
    user_id = uuid.UUID(res.json()["id"])
    
    # manually deactivate
    user = db_session.query(User).filter(User.id == user_id).first()
    user.is_active = False
    db_session.commit()

    login_res = client.post("/auth/login", json={"email": "grace@example.com", "password": "password123"})
    assert login_res.status_code == 403
