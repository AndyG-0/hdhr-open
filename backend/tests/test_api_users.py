from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import users as users_api
from app.auth import SESSION_COOKIE_NAME
from app.storage import db


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(users_api.router)
    return TestClient(app)


def test_list_profiles_is_empty_on_a_fresh_install(client, tmp_db):
    response = client.get("/api/users")

    assert response.status_code == 200
    assert response.json() == []


def test_create_profile_logs_the_new_user_in(client, tmp_db):
    response = client.post("/api/users", json={"name": "Alice", "avatar": "cat.png"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Alice"
    assert body["avatar"] == "cat.png"
    assert SESSION_COOKIE_NAME in response.cookies

    me = client.get("/api/users/me")
    assert me.status_code == 200
    assert me.json()["name"] == "Alice"


def test_create_profile_rejects_a_malformed_pin(client, tmp_db):
    response = client.post("/api/users", json={"name": "Alice", "pin": "abc"})

    assert response.status_code == 422


def test_login_with_no_pin_set_succeeds_without_a_pin(client, tmp_db):
    profile = client.post("/api/users", json={"name": "Alice"}).json()
    client.post("/api/users/logout")

    response = client.post(f"/api/users/{profile['id']}/login", json={})

    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies


def test_login_for_an_unknown_profile_returns_404(client, tmp_db):
    response = client.post("/api/users/nope/login", json={})

    assert response.status_code == 404


def test_login_with_a_pin_requires_the_correct_pin(client, tmp_db):
    client.post("/api/users", json={"name": "Bob", "pin": "1234"})
    client.post("/api/users/logout")

    wrong = client.post(f"/api/users/{db.list_users()[-1]['id']}/login", json={"pin": "0000"})
    assert wrong.status_code == 401

    correct = client.post(f"/api/users/{db.list_users()[-1]['id']}/login", json={"pin": "1234"})
    assert correct.status_code == 200


def test_login_locks_out_after_too_many_wrong_pins(client, tmp_db):
    client.post("/api/users", json={"name": "Bob", "pin": "1234"})
    client.post("/api/users/logout")
    user_id = db.list_users()[-1]["id"]

    for _ in range(5):
        response = client.post(f"/api/users/{user_id}/login", json={"pin": "0000"})
        assert response.status_code == 401

    locked = client.post(f"/api/users/{user_id}/login", json={"pin": "0000"})
    assert locked.status_code == 429

    still_locked = client.post(f"/api/users/{user_id}/login", json={"pin": "1234"})
    assert still_locked.status_code == 429


def test_login_lockout_is_scoped_per_profile(client, tmp_db):
    client.post("/api/users", json={"name": "Bob", "pin": "1234"})
    client.post("/api/users", json={"name": "Alice", "pin": "5678"})
    client.post("/api/users/logout")
    users = {u["name"]: u["id"] for u in db.list_users()}

    for _ in range(5):
        client.post(f"/api/users/{users['Bob']}/login", json={"pin": "0000"})
    assert client.post(f"/api/users/{users['Bob']}/login", json={"pin": "1234"}).status_code == 429

    other = client.post(f"/api/users/{users['Alice']}/login", json={"pin": "5678"})
    assert other.status_code == 200


def test_login_success_resets_the_failed_attempt_count(client, tmp_db):
    client.post("/api/users", json={"name": "Bob", "pin": "1234"})
    client.post("/api/users/logout")
    user_id = db.list_users()[-1]["id"]

    for _ in range(4):
        client.post(f"/api/users/{user_id}/login", json={"pin": "0000"})
    assert client.post(f"/api/users/{user_id}/login", json={"pin": "1234"}).status_code == 200

    for _ in range(4):
        response = client.post(f"/api/users/{user_id}/login", json={"pin": "0000"})
        assert response.status_code == 401


def test_logout_clears_the_session(client, tmp_db):
    client.post("/api/users", json={"name": "Alice"})

    response = client.post("/api/users/logout")

    assert response.status_code == 200
    assert client.get("/api/users/me").status_code == 401


def test_logout_without_a_session_still_succeeds(client, tmp_db):
    response = client.post("/api/users/logout")

    assert response.status_code == 200


def test_me_requires_a_session(client, tmp_db):
    response = client.get("/api/users/me")

    assert response.status_code == 401


def test_patch_me_updates_name_and_avatar(client, tmp_db):
    client.post("/api/users", json={"name": "Alice"})

    response = client.patch("/api/users/me", json={"name": "Renamed", "avatar": "dog.png"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["avatar"] == "dog.png"


def test_patch_me_can_set_and_then_clear_a_pin(client, tmp_db):
    profile = client.post("/api/users", json={"name": "Alice"}).json()

    client.patch("/api/users/me", json={"pin": "4321"})
    assert db.get_user(profile["id"])["pin_hash"] is not None

    client.patch("/api/users/me", json={"pin": ""})
    assert db.get_user(profile["id"])["pin_hash"] is None


def test_delete_me_refuses_to_delete_the_only_remaining_profile(client, tmp_db):
    client.post("/api/users", json={"name": "Alice"})

    response = client.delete("/api/users/me")

    assert response.status_code == 400


def test_delete_me_succeeds_when_another_profile_exists(client, tmp_db):
    client.post("/api/users", json={"name": "Alice"})
    bob = client.post("/api/users", json={"name": "Bob"}).json()

    response = client.delete("/api/users/me")

    assert response.status_code == 200
    assert db.get_user(bob["id"]) is None


def test_get_and_patch_preferences_round_trip(client, tmp_db):
    client.post("/api/users", json={"name": "Alice"})

    defaults = {"theme": "dark", "locale": "en"}
    assert client.get("/api/users/me/preferences").json() == defaults

    response = client.patch("/api/users/me/preferences", json={"theme": "light"})

    assert response.status_code == 200
    assert response.json() == {**defaults, "theme": "light"}
    assert client.get("/api/users/me/preferences").json() == {**defaults, "theme": "light"}


def test_patch_preferences_round_trips_locale(client, tmp_db):
    client.post("/api/users", json={"name": "Alice"})

    response = client.patch("/api/users/me/preferences", json={"locale": "es"})

    assert response.status_code == 200
    assert response.json()["locale"] == "es"
    assert client.get("/api/users/me/preferences").json()["locale"] == "es"
