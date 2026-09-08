import XCTest
@testable import HDHROpenKit

@MainActor
final class PlayerViewModelRecordingFlowTests: XCTestCase {
    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    private func makeMockedViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        return PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
    }

    // MARK: - playRecording

    func testPlayRecordingFailsWithoutAPlayableURL() async {
        let vm = makeMockedViewModel()
        let recording = HDHomeRunRecording(title: "No URL")

        await vm.playRecording(recording)

        if case .failed = vm.playerEngine.state {} else {
            XCTFail("expected .failed state, got \(vm.playerEngine.state)")
        }
    }

    func testPlayRecordingSuccessLoadsHLSSessionAndMetadata() async {
        let vm = makeMockedViewModel()
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\": \"sess-1\", \"playlist_url\": \"/api/hls/sess-1/playlist.m3u8\"}".utf8), 200
        )
        let detailBody = """
        {"is_in_progress": false, "duration_seconds": 300.0, "video": {"codec": "h264"}, "audio": [], "has_captions": false, "transcode": {"transcoding": false, "hardware": false}}
        """
        MockURLProtocol.handlers["/api/dvr/recording-detail"] = (Data(detailBody.utf8), 200)

        let recording = HDHomeRunRecording(recordingId: "rec-1", title: "A Recording", playUrl: "http://hdhr/rec.mpg")
        await vm.playRecording(recording)

        XCTAssertEqual(vm.activeHLSSessionId, "sess-1")
        if case .serverTranscodedHls = vm.playbackMode {} else {
            XCTFail("expected .serverTranscodedHls, got \(String(describing: vm.playbackMode))")
        }

        // loadRecordingMetadata dispatches its network fetches in a detached Task.
        try? await Task.sleep(nanoseconds: 150_000_000)
        XCTAssertEqual(vm.playerEngine.duration, 300.0, accuracy: 0.01)
    }

    func testPlayRecordingHandlesHLSSessionFailureGracefully() async {
        let vm = makeMockedViewModel()
        // No handler registered - MockURLProtocol returns 404 by default.
        let recording = HDHomeRunRecording(recordingId: "rec-1", title: "A Recording", playUrl: "http://hdhr/rec.mpg")

        await vm.playRecording(recording)

        if case .failed = vm.playerEngine.state {} else {
            XCTFail("expected .failed state, got \(vm.playerEngine.state)")
        }
        XCTAssertNil(vm.activeHLSSessionId)
    }

    // MARK: - promoteToRecording success path

    func testPromoteToRecordingSucceedsAfterAnActiveWatchSession() async {
        let vm = makeMockedViewModel()
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"session_id\": \"watch-1\", \"recording_id\": \"rec-watch\", \"title\": \"Live\", \"play_url\": \"http://hdhr/watch.mpg\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\": \"sess-2\", \"playlist_url\": \"/api/hls/sess-2/playlist.m3u8\"}".utf8), 200
        )
        let channel = HDHomeRunChannel(
            channelNumber: "4.1", name: "Test Channel", isHD: true, isDRM: false,
            streamUrl: "", playbackUrl: nil, now: nil, next: nil
        )
        await vm.playChannel(channel: channel)
        XCTAssertTrue(vm.isWatchSession)

        MockURLProtocol.handlers["/api/watch/watch-1/promote"] = (
            Data("{\"recording_id\": \"rec-watch\", \"title\": \"Promoted\"}".utf8), 200
        )

        await vm.promoteToRecording()

        XCTAssertTrue(vm.isPromoted)
        XCTAssertEqual(vm.activeRecording?.title, "Promoted")
    }

    // MARK: - selectAudioTrack

    func testSelectAudioTrackSwitchesSessionForActiveChannel() async {
        let vm = makeMockedViewModel()
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (Data("{\"detail\":\"no free tuner\"}".utf8), 503)
        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (
            Data("{\"session_id\": \"sess-1\", \"playlist_url\": \"/api/hls/sess-1/playlist.m3u8\", \"title\": \"Test Channel\"}".utf8), 200
        )
        let channel = HDHomeRunChannel(
            channelNumber: "4.1", name: "Test Channel", isHD: true, isDRM: false,
            streamUrl: "", playbackUrl: nil, now: nil, next: nil
        )
        await vm.playChannel(channel: channel)
        XCTAssertEqual(vm.activeHLSSessionId, "sess-1")

        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (
            Data("{\"session_id\": \"sess-2\", \"playlist_url\": \"/api/hls/sess-2/playlist.m3u8\", \"title\": \"Test Channel\"}".utf8), 200
        )
        let track = HDHomeRunRecordingAudioInfo(index: 1, language: "es")

        await vm.selectAudioTrack(track)

        XCTAssertEqual(vm.activeHLSSessionId, "sess-2")
        XCTAssertFalse(vm.isSwitchingAudioTrack)
    }

    func testSelectAudioTrackSwitchesSessionForActiveRecording() async {
        let vm = makeMockedViewModel()
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\": \"sess-1\", \"playlist_url\": \"/api/hls/sess-1/playlist.m3u8\"}".utf8), 200
        )
        let recording = HDHomeRunRecording(recordingId: "rec-1", title: "A Recording", playUrl: "http://hdhr/rec.mpg")
        await vm.playRecording(recording)
        XCTAssertEqual(vm.activeHLSSessionId, "sess-1")

        let track = HDHomeRunRecordingAudioInfo(index: 2)
        await vm.selectAudioTrack(track)

        // Same handler returns the same session id on the switch call too -
        // this exercises the recording branch of selectAudioTrack (as opposed
        // to the channel branch covered above) without needing a second stub.
        XCTAssertEqual(vm.activeHLSSessionId, "sess-1")
    }

    func testSelectAudioTrackFailsSilentlyWhenChannelSwitchHasNoSessionId() async {
        let vm = makeMockedViewModel()
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (Data("{\"detail\":\"no free tuner\"}".utf8), 503)
        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (
            Data("{\"session_id\": \"sess-1\", \"playlist_url\": \"/api/hls/sess-1/playlist.m3u8\", \"title\": \"Test Channel\"}".utf8), 200
        )
        let channel = HDHomeRunChannel(
            channelNumber: "4.1", name: "Test Channel", isHD: true, isDRM: false,
            streamUrl: "", playbackUrl: nil, now: nil, next: nil
        )
        await vm.playChannel(channel: channel)

        // No session_id in the response for the switch call.
        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (Data("{\"title\": \"\"}".utf8), 200)
        let track = HDHomeRunRecordingAudioInfo(index: 3)

        await vm.selectAudioTrack(track)

        XCTAssertEqual(vm.activeHLSSessionId, "sess-1")
    }
}
