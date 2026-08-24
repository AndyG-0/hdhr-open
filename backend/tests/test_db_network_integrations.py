from __future__ import annotations

import json
import sqlite3

from app.storage import db


def test_save_and_get_round_trips_settings(tmp_db):
    db.save_network_integration("pihole", "pihole", "Pi-hole", {"host": "pi.local", "port": 80, "password": "secret"})

    row = db.get_network_integration("pihole")

    assert row == {
        "id": "pihole",
        "type": "pihole",
        "name": "Pi-hole",
        "settings": {"host": "pi.local", "port": 80, "password": "secret"},
    }


def test_get_unknown_id_returns_none(tmp_db):
    assert db.get_network_integration("nope") is None


def test_save_upserts_by_id(tmp_db):
    db.save_network_integration("pihole", "pihole", "Pi-hole", {"host": "old.local"})
    db.save_network_integration("pihole", "pihole", "Pi-hole", {"host": "new.local"})

    row = db.get_network_integration("pihole")

    assert row["settings"] == {"host": "new.local"}


def test_secrets_are_encrypted_at_rest(tmp_db):
    db.save_network_integration(
        "pihole", "pihole", "Pi-hole", {"host": "pi.local", "password": "super-secret-password"}
    )

    conn = sqlite3.connect(tmp_db)
    raw = conn.execute("SELECT settings FROM network_integrations WHERE id = ?", ("pihole",)).fetchone()[0]
    conn.close()
    stored = json.loads(raw)

    assert stored["host"] == "pi.local"
    assert "super-secret-password" not in raw
    assert stored["password"] != "super-secret-password"

    decrypted = db.get_network_integration("pihole")
    assert decrypted["settings"]["password"] == "super-secret-password"


def test_non_secret_fields_are_stored_in_plaintext(tmp_db):
    db.save_network_integration("pihole", "pihole", "Pi-hole", {"host": "pi.local", "port": 80})

    conn = sqlite3.connect(tmp_db)
    raw = conn.execute("SELECT settings FROM network_integrations WHERE id = ?", ("pihole",)).fetchone()[0]
    conn.close()

    assert "pi.local" in raw


def test_empty_secret_value_is_not_encrypted(tmp_db):
    db.save_network_integration("pihole", "pihole", "Pi-hole", {"host": "pi.local", "password": ""})

    row = db.get_network_integration("pihole")

    assert row["settings"]["password"] == ""


def test_list_network_integrations_returns_all_by_default(tmp_db):
    db.save_network_integration("pihole", "pihole", "Pi-hole", {"host": "pi.local"})
    db.save_network_integration("container-abc12345", "container", "Docker Test Host", {"engine": "docker"})

    rows = db.list_network_integrations()

    ids = {r["id"] for r in rows}
    assert "pihole" in ids
    assert "container-abc12345" in ids


def test_list_network_integrations_filters_by_type(tmp_db):
    # dashboard.yaml (read by migration 007, which runs as part of tmp_db's
    # db.init_db()) may already define its own container widgets — this only
    # asserts that "pihole" is excluded and our own rows are present.
    db.save_network_integration("pihole", "pihole", "Pi-hole", {"host": "pi.local"})
    db.save_network_integration("container-abc12345", "container", "Docker Test Host", {"engine": "docker"})
    db.save_network_integration("container-def67890", "container", "Podman Test Host", {"engine": "podman"})

    rows = db.list_network_integrations("container")

    ids = {r["id"] for r in rows}
    assert {"container-abc12345", "container-def67890"} <= ids
    assert "pihole" not in ids
    assert all(r["type"] == "container" for r in rows)


def test_delete_network_integration_removes_row(tmp_db):
    db.save_network_integration("pihole", "pihole", "Pi-hole", {"host": "pi.local"})

    db.delete_network_integration("pihole")

    assert db.get_network_integration("pihole") is None


def test_delete_network_integration_unknown_id_is_a_no_op(tmp_db):
    db.delete_network_integration("nope")
