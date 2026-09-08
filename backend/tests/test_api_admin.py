from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import admin as admin_api
from app.auth import get_current_admin, get_current_user
from app.storage import db


@pytest.fixture
def client(tmp_db):
    app = FastAPI()
    app.include_router(admin_api.router)
    return TestClient(app)


def _seed_users():
    db.create_user("admin1", "Admin", None, None, None, None, "2026-01-01T00:00:00Z", role="admin")
    db.create_user("member1", "Member", None, None, None, None, "2026-01-02T00:00:00Z", role="member")


def test_admin_routes_require_a_session(client):
    _seed_users()

    assert client.get("/api/admin/users").status_code == 401


def test_admin_routes_reject_a_non_admin_session(client):
    _seed_users()
    client.app.dependency_overrides[get_current_user] = lambda: db.get_user("member1")

    assert client.get("/api/admin/users").status_code == 403


def test_list_household_users_includes_role_and_created_at(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.get("/api/admin/users")

    assert response.status_code == 200
    body = {u["id"]: u for u in response.json()}
    assert body["admin1"]["role"] == "admin"
    assert body["member1"]["role"] == "member"
    assert "created_at" in body["admin1"]
    assert "pin_hash" not in body["admin1"]


def test_promote_a_member_to_admin(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.patch("/api/admin/users/member1/role", json={"role": "admin"})

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert db.get_user("member1")["role"] == "admin"


def test_demote_the_last_admin_is_refused(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.patch("/api/admin/users/admin1/role", json={"role": "member"})

    assert response.status_code == 400
    assert db.get_user("admin1")["role"] == "admin"


def test_demote_an_admin_succeeds_when_another_admin_exists(client):
    _seed_users()
    db.update_user("member1", role="admin")
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.patch("/api/admin/users/admin1/role", json={"role": "member"})

    assert response.status_code == 200
    assert db.get_user("admin1")["role"] == "member"


def test_update_role_for_an_unknown_user_returns_404(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.patch("/api/admin/users/nope/role", json={"role": "admin"})

    assert response.status_code == 404


def test_delete_a_member_succeeds(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.delete("/api/admin/users/member1")

    assert response.status_code == 200
    assert db.get_user("member1") is None


def test_delete_yourself_via_this_route_is_refused(client):
    _seed_users()
    db.update_user("member1", role="admin")
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.delete("/api/admin/users/admin1")

    assert response.status_code == 400


def test_create_household_user_success(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.post("/api/admin/users", json={"name": "Charlie", "avatar": "🦊", "role": "member"})

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Charlie"
    assert data["avatar"] == "🦊"
    assert data["role"] == "member"
    assert data["has_pin"] is False
    assert "id" in data

    stored = db.get_user(data["id"])
    assert stored is not None
    assert stored["name"] == "Charlie"
    assert stored["pin_hash"] is None


def test_create_household_user_with_pin(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.post(
        "/api/admin/users",
        json={"name": "Bob", "avatar": None, "role": "admin", "pin": "1234"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Bob"
    assert data["role"] == "admin"
    assert data["has_pin"] is True

    stored = db.get_user(data["id"])
    assert stored is not None
    assert stored["pin_hash"] is not None


def test_create_household_user_validation(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    # Empty name
    res1 = client.post("/api/admin/users", json={"name": "   "})
    assert res1.status_code == 400

    # Non-digit PIN
    res2 = client.post("/api/admin/users", json={"name": "Test", "pin": "abcd"})
    assert res2.status_code == 422

    # Too short PIN (<4 digits)
    res3 = client.post("/api/admin/users", json={"name": "Test", "pin": "12"})
    assert res3.status_code == 422


def test_update_household_user_details(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.patch(
        "/api/admin/users/member1",
        json={"name": "Member Renamed", "avatar": "🌟"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Member Renamed"
    assert data["avatar"] == "🌟"
    assert data["role"] == "member"

    stored = db.get_user("member1")
    assert stored["name"] == "Member Renamed"
    assert stored["avatar"] == "🌟"


def test_update_household_user_reset_and_clear_pin(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    # Set PIN
    res1 = client.patch("/api/admin/users/member1", json={"pin": "9876"})
    assert res1.status_code == 200
    assert res1.json()["has_pin"] is True
    assert db.get_user("member1")["pin_hash"] is not None

    # Clear PIN
    res2 = client.patch("/api/admin/users/member1", json={"pin": ""})
    assert res2.status_code == 200
    assert res2.json()["has_pin"] is False
    assert db.get_user("member1")["pin_hash"] is None


def test_update_household_user_cannot_demote_last_admin(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.patch("/api/admin/users/admin1", json={"role": "member"})
    assert response.status_code == 400
    assert "last remaining admin" in response.json()["detail"]


def test_update_household_user_404_unknown(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")

    response = client.patch("/api/admin/users/ghost", json={"name": "Ghost"})
    assert response.status_code == 404

