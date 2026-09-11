import XCTest
@testable import HDHROpenKit

@MainActor
final class PlayerViewModelSyncPlayRoomTests: XCTestCase {
    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    private func makeMockedViewModel() -> (PlayerViewModel, APIClient) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
        return (vm, apiClient)
    }

    // MARK: - createSyncPlayRoom / joinSyncPlayRoom / leaveSyncPlayRoom / transferSyncPlayHost

    func testCreateSyncPlayRoomConnectsToReturnedWebSocketURL() async throws {
        let (vm, _) = makeMockedViewModel()
        let body = """
        {
            "room": {
                "room_code": "ABC123",
                "host_session_id": "host-1",
                "created_at": 1000.0
            }
        }
        """
        MockURLProtocol.handlers["/api/syncplay/rooms"] = (Data(body.utf8), 200)

        let room = try await vm.createSyncPlayRoom(userName: "Alice")

        XCTAssertEqual(room.roomCode, "ABC123")
        XCTAssertTrue(vm.syncPlayClient.isConnected)
    }

    func testJoinSyncPlayRoomConnectsWebSocket() async throws {
        let (vm, _) = makeMockedViewModel()

        try await vm.joinSyncPlayRoom(roomCode: "XYZ999", userName: "Bob")

        XCTAssertTrue(vm.syncPlayClient.isConnected)
    }

    func testLeaveSyncPlayRoomDisconnects() async throws {
        let (vm, _) = makeMockedViewModel()
        try await vm.joinSyncPlayRoom(roomCode: "XYZ999", userName: "Bob")
        XCTAssertTrue(vm.syncPlayClient.isConnected)

        vm.leaveSyncPlayRoom()

        XCTAssertFalse(vm.syncPlayClient.isConnected)
    }

    func testTransferSyncPlayHostForwardsToClientWithoutCrashing() async throws {
        let (vm, _) = makeMockedViewModel()
        try await vm.joinSyncPlayRoom(roomCode: "XYZ999", userName: "Bob")

        vm.transferSyncPlayHost(targetSessionId: "other-session")

        // No observable state change without a real room/host response - this
        // only verifies the forwarding call is reachable and doesn't crash.
        XCTAssertTrue(vm.syncPlayClient.isConnected)
    }

    // MARK: - startSharePlayOnTV / leaveSharePlaySession

    func testStartSharePlayOnTVIsNoOpWhenNothingIsPlaying() async {
        let (vm, _) = makeMockedViewModel()

        await vm.startSharePlayOnTV()

        XCTAssertFalse(vm.sharePlayCoordinator.isSessionActive)
    }

    func testLeaveSharePlaySessionForwardsToCoordinatorWithoutCrashing() {
        let (vm, _) = makeMockedViewModel()

        vm.leaveSharePlaySession()

        XCTAssertFalse(vm.sharePlayCoordinator.isSessionActive)
    }

    // MARK: - handleRemoteContentChange (via syncPlayClient.onRemoteContentChange)

    func testRemoteContentChangeToNewRecordingStartsPlaybackViaPlayRecording() async throws {
        let (vm, _) = makeMockedViewModel()
        let content = SyncPlayContent(type: "recording", recordingId: "rec-42", channelNumber: nil, title: "Remote Recording", durationSeconds: nil)

        vm.syncPlayClient.onRemoteContentChange?(content)
        // handleRemoteContentChange dispatches through nested Tasks - poll
        // rather than guessing a fixed delay is enough for them to run.
        try await pollUntil { vm.activeRecording?.recordingId == "rec-42" }

        XCTAssertEqual(vm.activeRecording?.recordingId, "rec-42")
    }

    func testRemoteContentChangeToNewChannelStartsPlaybackViaPlayChannel() async throws {
        let (vm, _) = makeMockedViewModel()
        let content = SyncPlayContent(type: "channel", recordingId: nil, channelNumber: "9.1", title: "Remote Channel", durationSeconds: nil)

        vm.syncPlayClient.onRemoteContentChange?(content)
        try await pollUntil { vm.activeChannel?.channelNumber == "9.1" }

        XCTAssertEqual(vm.activeChannel?.channelNumber, "9.1")
    }

    func testRemoteContentChangeIsNoOpWhenAlreadyOnThatRecording() async throws {
        let (vm, apiClient) = makeMockedViewModel()
        let hlsBody = """
        {"session_id": "sess-1", "playlist_url": "/api/hls/sess-1/playlist.m3u8"}
        """
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (Data(hlsBody.utf8), 200)
        let existing = HDHomeRunRecording(recordingId: "rec-42", title: "Already Playing", playUrl: "http://hdhr/rec.mpg")
        await vm.playRecording(existing)
        _ = apiClient
        XCTAssertEqual(vm.activeRecording?.recordingId, "rec-42")

        let content = SyncPlayContent(type: "recording", recordingId: "rec-42", channelNumber: nil, title: "Duplicate", durationSeconds: nil)
        vm.syncPlayClient.onRemoteContentChange?(content)
        try await Task.sleep(nanoseconds: 100_000_000)

        // Title should remain from the original playRecording call, not be
        // replaced by a dummy reconstructed from the (ignored) duplicate content change.
        XCTAssertEqual(vm.activeRecording?.title, "Already Playing")
    }
}
