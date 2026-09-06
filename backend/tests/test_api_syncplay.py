from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.syncplay import hub
from app.main import app


def test_syncplay_rest_room_crud(tmp_db):
    hub.rooms.clear()
    with TestClient(app) as client:
        # Create room
        payload = {
            "content": {
                "type": "channel",
                "id": "5.1",
                "title": "NBC News",
                "channel_number": "5.1",
                "play_url": "http://example.com/stream",
            }
        }
        res = client.post("/api/syncplay/rooms", json=payload)
        assert res.status_code == 200
        data = res.json()
        room_code = data["room_code"]
        assert len(room_code) == 6
        assert data["room"]["content"]["title"] == "NBC News"
        assert data["room"]["content"]["channel_number"] == "5.1"

        # Get room
        get_res = client.get(f"/api/syncplay/rooms/{room_code}")
        assert get_res.status_code == 200
        assert get_res.json()["room_code"] == room_code

        # List rooms
        list_res = client.get("/api/syncplay/rooms")
        assert list_res.status_code == 200
        rooms = list_res.json()
        assert any(r["room_code"] == room_code for r in rooms)

        # 404 for invalid room
        res_404 = client.get("/api/syncplay/rooms/NONEXIST")
        assert res_404.status_code == 404


def test_syncplay_websocket_flow(tmp_db):
    hub.rooms.clear()
    with TestClient(app) as client:
        # Create a room
        res = client.post(
            "/api/syncplay/rooms",
            json={
                "content": {
                    "type": "recording",
                    "id": "rec_123",
                    "title": "Documentary",
                }
            },
        )
        room_code = res.json()["room_code"]

        # Connect Host via WebSocket
        with client.websocket_connect(f"/api/syncplay/ws/{room_code}?user_name=Alice") as ws_host:
            host_state = ws_host.receive_json()
            assert host_state["type"] == "room_state"
            assert host_state["room"]["room_code"] == room_code
            host_session_id = host_state["your_session_id"]
            assert host_state["room"]["host_session_id"] == host_session_id

            # Connect Peer via WebSocket
            with client.websocket_connect(f"/api/syncplay/ws/{room_code}?user_name=Bob") as ws_peer:
                peer_state = ws_peer.receive_json()
                assert peer_state["type"] == "room_state"
                peer_session_id = peer_state["your_session_id"]

                # Host receives participant_joined
                joined_event = ws_host.receive_json()
                assert joined_event["type"] == "participant_joined"
                assert joined_event["participant"]["user_name"] == "Bob"

                # Peer sends ping
                ws_peer.send_json({"type": "ping", "client_time": 1234.5})
                pong_event = ws_peer.receive_json()
                assert pong_event["type"] == "pong"
                assert pong_event["client_time"] == 1234.5

                # Host issues play
                ws_host.send_json({"type": "play", "position": 10.5, "playback_rate": 1.0})
                host_play = ws_host.receive_json()
                peer_play = ws_peer.receive_json()
                assert host_play["type"] == "playback_update"
                assert host_play["action"] == "play"
                assert host_play["position"] == 10.5
                assert peer_play["type"] == "playback_update"
                assert peer_play["action"] == "play"
                assert peer_play["position"] == 10.5

                # Peer issues pause
                ws_peer.send_json({"type": "pause", "position": 25.0})
                host_pause = ws_host.receive_json()
                peer_pause = ws_peer.receive_json()
                assert host_pause["type"] == "playback_update"
                assert host_pause["action"] == "pause"
                assert host_pause["position"] == 25.0
                assert peer_pause["position"] == 25.0

                # Host issues seek
                ws_host.send_json({"type": "seek", "position": 100.0})
                host_seek = ws_host.receive_json()
                peer_seek = ws_peer.receive_json()
                assert host_seek["action"] == "seek"
                assert host_seek["position"] == 100.0
                assert peer_seek["position"] == 100.0

                # Peer sends progress
                ws_peer.send_json({"type": "progress", "position": 100.0, "is_ready": True, "ping_ms": 15.0})
                peer_updated = ws_host.receive_json()
                assert peer_updated["type"] == "participant_updated"
                assert peer_updated["participant"]["session_id"] == peer_session_id
                assert peer_updated["participant"]["ping_ms"] == 15.0

                # Host changes content
                ws_host.send_json({
                    "type": "change_content",
                    "content": {
                        "type": "channel",
                        "id": "7.1",
                        "title": "ABC World News",
                        "channel_number": "7.1",
                    },
                })
                host_content = ws_host.receive_json()
                peer_content = ws_peer.receive_json()
                assert host_content["type"] == "content_changed"
                assert host_content["content"]["title"] == "ABC World News"
                assert peer_content["content"]["title"] == "ABC World News"

            # Peer leaves, host gets participant_left
            left_event = ws_host.receive_json()
            assert left_event["type"] == "participant_left"
            assert left_event["session_id"] == peer_session_id


def test_syncplay_host_election_on_disconnect(tmp_db):
    hub.rooms.clear()
    with TestClient(app) as client:
        res = client.post(
            "/api/syncplay/rooms",
            json={
                "content": {
                    "type": "channel",
                    "id": "2.1",
                    "title": "CBS",
                }
            },
        )
        room_code = res.json()["room_code"]

        with client.websocket_connect(f"/api/syncplay/ws/{room_code}?user_name=HostAlice") as ws_host:
            host_state = ws_host.receive_json()
            host_session_id = host_state["your_session_id"]

            with client.websocket_connect(f"/api/syncplay/ws/{room_code}?user_name=PeerBob") as ws_peer:
                peer_state = ws_peer.receive_json()
                peer_session_id = peer_state["your_session_id"]
                ws_host.receive_json()  # participant_joined

                # Host transfers host to PeerBob
                ws_host.send_json({"type": "transfer_host", "target_session_id": peer_session_id})
                host_change_host = ws_host.receive_json()
                peer_change_host = ws_peer.receive_json()
                assert host_change_host["type"] == "host_changed"
                assert host_change_host["new_host_session_id"] == peer_session_id
                assert peer_change_host["new_host_session_id"] == peer_session_id
