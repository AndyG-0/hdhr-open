import XCTest
@testable import HDHROpenKit

@MainActor
final class ChannelStreamNegotiatorTests: XCTestCase {
    private func makeAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    private func makeChannel(_ number: String = "4.1", name: String = "NBC") -> HDHomeRunChannel {
        HDHomeRunChannel(channelNumber: number, name: name)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        MockURLProtocol.resetLog()
        MockURLProtocol.resetGates()
        MockURLProtocol.resetQueues()
        super.tearDown()
    }

    func testNegotiateChannelPrefersWatchSession() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"watch1\",\"title\":\"NBC\",\"play_url\":\"/stream/4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\":\"hls1\",\"playlist_url\":\"/api/streaming/hls/hls1/playlist.m3u8\"}".utf8), 200
        )

        let client = makeAPIClient()
        let negotiator = ChannelStreamNegotiator(apiClient: client, watchSessionManager: WatchSessionManager(apiClient: client))

        let result = try await negotiator.negotiate(.channel(makeChannel()))

        XCTAssertTrue(result.isWatchSession)
        XCTAssertEqual(result.hlsSessionId, "hls1")
        XCTAssertEqual(result.watchSessionId, "watch1")
        XCTAssertEqual(result.recording?.recordingId, "rec1")
        XCTAssertTrue(result.isSeekable)
    }

    func testNegotiateChannelFallsBackToDirectHLSWhenWatchSessionFails() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (Data("{\"detail\":\"no free tuner\"}".utf8), 503)
        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (
            Data("{\"title\":\"\",\"session_id\":\"hls2\",\"playlist_url\":\"/api/streaming/hls/hls2/playlist.m3u8\"}".utf8), 200
        )

        let client = makeAPIClient()
        let negotiator = ChannelStreamNegotiator(apiClient: client, watchSessionManager: WatchSessionManager(apiClient: client))

        let result = try await negotiator.negotiate(.channel(makeChannel()))

        XCTAssertFalse(result.isWatchSession)
        XCTAssertEqual(result.hlsSessionId, "hls2")
        XCTAssertNil(result.watchSessionId)
        XCTAssertFalse(result.isSeekable)
    }

    func testTeardownStopsBothSessionsForWatchSessionResult() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"watch1\",\"title\":\"NBC\",\"play_url\":\"/stream/4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\":\"hls1\",\"playlist_url\":\"/api/streaming/hls/hls1/playlist.m3u8\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/watch1/stop"] = (Data("{}".utf8), 200)
        MockURLProtocol.handlers["/api/hls/hls1/stop"] = (Data("{}".utf8), 200)

        let client = makeAPIClient()
        let negotiator = ChannelStreamNegotiator(apiClient: client, watchSessionManager: WatchSessionManager(apiClient: client))
        let result = try await negotiator.negotiate(.channel(makeChannel()))

        negotiator.teardown(result)

        // `teardown(_:)`'s HLS stop is fire-and-forget (`runWithBackgroundGrace`), so poll
        // briefly rather than asserting immediately after the call returns.
        for _ in 0..<25 where !(
            MockURLProtocol.requestLog.contains("/api/hls/hls1/stop")
                && MockURLProtocol.requestLog.contains("/api/watch/watch1/stop")
        ) {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/hls/hls1/stop"))
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/watch/watch1/stop"))
    }

    func testTeardownStopsOnlyHLSSessionForDirectResult() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (Data("{\"detail\":\"no free tuner\"}".utf8), 503)
        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (
            Data("{\"title\":\"\",\"session_id\":\"hls2\",\"playlist_url\":\"/api/streaming/hls/hls2/playlist.m3u8\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/hls/hls2/stop"] = (Data("{}".utf8), 200)

        let client = makeAPIClient()
        let negotiator = ChannelStreamNegotiator(apiClient: client, watchSessionManager: WatchSessionManager(apiClient: client))
        let result = try await negotiator.negotiate(.channel(makeChannel()))

        negotiator.teardown(result)

        for _ in 0..<25 where !MockURLProtocol.requestLog.contains("/api/hls/hls2/stop") {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/hls/hls2/stop"))
        // No watch session was negotiated for the direct-HLS fallback, so nothing
        // should ever be posted to a watch-session stop endpoint.
        XCTAssertFalse(MockURLProtocol.requestLog.contains { $0.hasPrefix("/api/watch/") && $0.hasSuffix("/stop") })
    }

    func testNegotiateRecordingBuildsSeekableSession() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\":\"hls3\",\"playlist_url\":\"/api/streaming/hls/hls3/playlist.m3u8\"}".utf8), 200
        )

        let client = makeAPIClient()
        let negotiator = ChannelStreamNegotiator(apiClient: client, watchSessionManager: WatchSessionManager(apiClient: client))
        let recording = HDHomeRunRecording(
            recordingId: "rec9", title: "Recorded Show", channelNumber: "4.1", playUrl: "/stream/rec9"
        )

        let result = try await negotiator.negotiate(.recording(recording))

        XCTAssertEqual(result.hlsSessionId, "hls3")
        XCTAssertFalse(result.isWatchSession)
        XCTAssertNil(result.watchSessionId)
        XCTAssertTrue(result.isSeekable)
    }

    func testNegotiateRecordingWithoutPlayURLThrows() async throws {
        let client = makeAPIClient()
        let negotiator = ChannelStreamNegotiator(apiClient: client, watchSessionManager: WatchSessionManager(apiClient: client))
        let recording = HDHomeRunRecording(recordingId: "rec9", title: "Recorded Show", channelNumber: "4.1", playUrl: nil)

        do {
            _ = try await negotiator.negotiate(.recording(recording))
            XCTFail("Expected StreamNegotiationError.noPlayableURL")
        } catch StreamNegotiationError.noPlayableURL {
            // expected
        }
    }
}
