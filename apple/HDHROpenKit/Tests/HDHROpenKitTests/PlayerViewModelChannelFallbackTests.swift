import XCTest
@testable import HDHROpenKit

@MainActor
final class PlayerViewModelChannelFallbackTests: XCTestCase {
    private func makeChannel() -> HDHomeRunChannel {
        HDHomeRunChannel(
            channelNumber: "4.1",
            name: "Test Channel",
            isHD: true,
            isDRM: false,
            streamUrl: "",
            playbackUrl: nil,
            now: nil,
            next: nil
        )
    }

    private func makeMockedAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testPlayChannelFallbackLoadsRecordingMetadataWhenBackendReturnsRealCapture() async {
        // Watch session start fails (busy tuner) - forces the direct-HLS fallback branch.
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (Data("{\"detail\":\"no free tuner\"}".utf8), 503)

        // The fallback endpoint now backs the stream with a real temporary
        // capture, so it returns full recording metadata alongside the HLS
        // session fields (mirrors _format_builtin_recording's shape).
        let body = """
        {
            "recording_id": "rec_fallback",
            "title": "Test Channel",
            "channel_number": "4.1",
            "play_url": "/recorded/rec_fallback",
            "has_captions": true,
            "session_id": "sess-123",
            "playlist_url": "/api/hls/sess-123/playlist.m3u8"
        }
        """
        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (Data(body.utf8), 200)

        let apiClient = makeMockedAPIClient()
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))

        await vm.playChannel(channel: makeChannel())

        XCTAssertEqual(vm.activeHLSSessionId, "sess-123")
        XCTAssertFalse(vm.isWatchSession)
        if case .serverTranscodedHls = vm.playbackMode {} else {
            XCTFail("expected .serverTranscodedHls, got \(String(describing: vm.playbackMode))")
        }
        XCTAssertEqual(vm.activeRecording?.recordingId, "rec_fallback")
    }

    func testPlayChannelFallbackWithoutCaptureLeavesActiveRecordingNil() async {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (Data("{\"detail\":\"no free tuner\"}".utf8), 503)

        // Even the unmanaged capture couldn't start - the bare raw-URL pipe
        // safety net kicks in, with no recording metadata to attach.
        let body = """
        {
            "title": "",
            "session_id": "sess-456",
            "playlist_url": "/api/hls/sess-456/playlist.m3u8"
        }
        """
        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (Data(body.utf8), 200)

        let apiClient = makeMockedAPIClient()
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))

        await vm.playChannel(channel: makeChannel())

        XCTAssertEqual(vm.activeHLSSessionId, "sess-456")
        XCTAssertNil(vm.activeRecording)
    }
}
