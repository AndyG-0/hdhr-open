from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import users as users_api


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(users_api.router)
    return TestClient(app)


def test_full_register_login_logout_profile_switch_flow(client, tmp_db):
    # 1. Profile picker is empty on a fresh install — no profile is seeded.
    profiles = client.get("/api/users").json()
    assert profiles == []

    # 2. Create two real profiles.
    alice = client.post("/api/users", json={"name": "Alice"}).json()
    client.post("/api/users/logout")
    bob = client.post("/api/users", json={"name": "Bob"}).json()
    client.post("/api/users/logout")

    # 3. Alice logs in.
    login = client.post(f"/api/users/{alice['id']}/login", json={})
    assert login.json()["id"] == alice["id"]

    # 4. Bob logs in on the same client, replacing Alice's session.
    client.post("/api/users/logout")
    login = client.post(f"/api/users/{bob['id']}/login", json={})
    assert login.json()["id"] == bob["id"]


def test_users_me_requires_a_session(client, tmp_db):
    assert client.get("/api/users/me").status_code == 401

    profile = client.post("/api/users", json={"name": "Alice"}).json()
    client.post(f"/api/users/{profile['id']}/login", json={})
    assert client.get("/api/users/me").status_code == 200


def test_login_with_token_name_issues_a_bearer_token_usable_without_cookies(client, tmp_db):
    alice = client.post("/api/users", json={"name": "Alice"}).json()
    client.post("/api/users/logout")

    login = client.post(f"/api/users/{alice['id']}/login", json={"token_name": "Alice's iPhone"})
    token = login.json()["token"]
    assert token

    # A bare client with no cookies at all — the point of a bearer token.
    bare = TestClient(client.app)
    assert bare.get("/api/users/me").status_code == 401
    authed = bare.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert authed.status_code == 200
    assert authed.json()["id"] == alice["id"]


def test_login_without_token_name_does_not_issue_a_token(client, tmp_db):
    alice = client.post("/api/users", json={"name": "Alice"}).json()
    client.post("/api/users/logout")

    login = client.post(f"/api/users/{alice['id']}/login", json={})
    assert "token" not in login.json()


def test_bearer_token_lifecycle_list_and_revoke(client, tmp_db):
    alice = client.post("/api/users", json={"name": "Alice"}).json()
    login = client.post(f"/api/users/{alice['id']}/login", json={"token_name": "Alice's iPhone"}).json()
    token = login["token"]

    tokens = client.get("/api/users/me/tokens").json()
    assert len(tokens) == 1
    assert tokens[0]["name"] == "Alice's iPhone"
    assert "token" not in tokens[0]

    revoke = client.delete(f"/api/users/me/tokens/{tokens[0]['id']}")
    assert revoke.status_code == 200

    bare = TestClient(client.app)
    revoked = bare.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert revoked.status_code == 401


def test_bearer_token_revoke_requires_ownership(client, tmp_db):
    alice = client.post("/api/users", json={"name": "Alice"}).json()
    client.post("/api/users/logout")
    bob = client.post("/api/users", json={"name": "Bob"}).json()
    login = client.post(f"/api/users/{bob['id']}/login", json={"token_name": "Bob's TV"}).json()

    # Alice's session shouldn't be able to see or revoke Bob's token.
    alice_session = TestClient(client.app)
    alice_session.post(f"/api/users/{alice['id']}/login", json={})
    bob_tokens = alice_session.get("/api/users/me/tokens").json()
    assert bob_tokens == []

    bob_token_id = client.get("/api/users/me/tokens").json()[0]["id"]
    forbidden = alice_session.delete(f"/api/users/me/tokens/{bob_token_id}")
    assert forbidden.status_code == 404

    # The token is still valid — Alice's failed revoke attempt didn't touch it.
    bare = TestClient(client.app)
    assert bare.get("/api/users/me", headers={"Authorization": f"Bearer {login['token']}"}).status_code == 200
