import XCTest
@testable import HDHROpenKit

@MainActor
final class SyncPlayTests: XCTestCase {

    func testSyncPlayModelsEncodingDecoding() throws {
        let room = SyncPlayRoom(
            roomCode: "SWIFT1",
            hostSessionId: "host-sess-1",
            createdAt: 1000.0,
            playbackState: SyncPlayPlaybackState(isPlaying: true, position: 123.4, playbackRate: 1.0, updatedAt: 1005.0),
            currentContent: SyncPlayContent(type: "recording", recordingId: "rec-999", channelNumber: "7.1", title: "Swift Show", durationSeconds: 1800.0),
            participants: [
                SyncPlayParticipant(sessionId: "host-sess-1", userName: "Bob", isHost: true, isReady: true, position: 123.4, pingMs: 12.0)
            ]
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(room)

        let decoder = JSONDecoder()
        let decoded = try decoder.decode(SyncPlayRoom.self, from: data)

        XCTAssertEqual(decoded.roomCode, "SWIFT1")
        XCTAssertEqual(decoded.hostSessionId, "host-sess-1")
        XCTAssertTrue(decoded.playbackState.isPlaying)
        XCTAssertEqual(decoded.playbackState.position, 123.4, accuracy: 0.001)
        XCTAssertEqual(decoded.currentContent?.recordingId, "rec-999")
        XCTAssertEqual(decoded.participants.count, 1)
        XCTAssertEqual(decoded.participants.first?.userName, "Bob")
        XCTAssertTrue(decoded.participants.first?.isHost == true)
    }

    func testSyncPlayClientMessageHandling() {
        let client = SyncPlayClient()

        var remotePlayed = false
        var remotePlayPos = 0.0
        client.onRemotePlay = { pos, _ in
            remotePlayed = true
            remotePlayPos = pos
        }

        // Handle room_state
        let roomStateJson = """
        {
            "type": "room_state",
            "your_session_id": "my-sess-id",
            "room": {
                "room_code": "ABC789",
                "host_session_id": "other-sess-id",
                "created_at": 100.0,
                "playback_state": {
                    "is_playing": false,
                    "position": 0.0,
                    "playback_rate": 1.0
                },
                "participants": [
                    {"session_id": "other-sess-id", "user_name": "HostUser", "is_host": true},
                    {"session_id": "my-sess-id", "user_name": "Me", "is_host": false}
                ]
            }
        }
        """

        client.handleRawMessage(roomStateJson)

        XCTAssertEqual(client.room?.roomCode, "ABC789")
        XCTAssertEqual(client.sessionId, "my-sess-id")
        XCTAssertFalse(client.isHost)
        XCTAssertEqual(client.participants.count, 2)

        // Handle playback update
        let playbackUpdateJson = """
        {
            "type": "playback_update",
            "action": "play",
            "position": 45.5,
            "playback_rate": 1.0,
            "is_playing": true,
            "triggered_by": "other-sess-id"
        }
        """

        client.handleRawMessage(playbackUpdateJson)

        XCTAssertTrue(remotePlayed)
        XCTAssertEqual(remotePlayPos, 45.5, accuracy: 0.001)
        XCTAssertTrue(client.room?.playbackState.isPlaying == true)
        XCTAssertEqual(client.room?.playbackState.position ?? 0.0, 45.5, accuracy: 0.001)
    }

    func testPlayerViewModelSyncPlayWiring() {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!)
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
        vm.playerEngine.loadMedia(url: URL(string: "http://localhost:8000/test.m3u8")!, isSeekable: true)

        XCTAssertNotNil(vm.syncPlayClient)
        XCTAssertNil(vm.syncPlayClient.room)
        XCTAssertFalse(vm.syncPlayClient.isConnected)

        // Remote playback callbacks
        vm.syncPlayClient.onRemotePlay?(15.0, 1.0)
        XCTAssertEqual(vm.playerEngine.currentTime, 15.0, accuracy: 0.001)

        vm.syncPlayClient.onRemotePause?(25.0)
        XCTAssertEqual(vm.playerEngine.currentTime, 25.0, accuracy: 0.001)

        vm.syncPlayClient.onRemoteSeek?(40.0)
        XCTAssertEqual(vm.playerEngine.currentTime, 40.0, accuracy: 0.001)
    }

    func testAPIEndpointsSyncPlay() {
        XCTAssertEqual(APIEndpoints.syncPlayRooms(), "/api/syncplay/rooms")
        XCTAssertEqual(APIEndpoints.syncPlayRoom("ABCDEF"), "/api/syncplay/rooms/ABCDEF")
        let wsUrl = APIEndpoints.syncPlayWs(roomCode: "XYZ123", userName: "John Doe")
        XCTAssertTrue(wsUrl.contains("/api/syncplay/ws/XYZ123"))
        XCTAssertTrue(wsUrl.contains("user_name=John%20Doe"))
    }
}
