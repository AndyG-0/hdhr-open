import XCTest
@testable import HDHROpenKit

/// REV-APL-10: regression coverage for the negotiation-generation guard added to
/// `StreamSessionCoordinator` (REV-APL-3's `PlayerViewModel` half) and the
/// cancellable `metadataTask` in `loadRecordingMetadata` (REV-APL-7). Mirrors the
/// gate-based race tests already covering the equivalent `MultiPlayerViewModel`
/// guards in `MultiPlayerViewModelTests.swift`.
@MainActor
final class PlayerViewModelCancellationTests: XCTestCase {
    private func makeMockedViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        return PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        MockURLProtocol.resetLog()
        MockURLProtocol.resetGates()
        MockURLProtocol.resetQueues()
        super.tearDown()
    }

    /// Two rapid `playChannel` calls (e.g. a double-tap in the guide) with no
    /// stored task to cancel the first: without the generation guard, the
    /// stale first negotiation would either overwrite the second channel's
    /// state after the fact, or - if the second wins the race, as here -
    /// leak the backend session the first call negotiated. Gate the first
    /// channel's watch-session start so the second, ungated call is
    /// guaranteed to land first.
    func testSupersededPlayChannelTearsDownStaleNegotiationInsteadOfLeakingIt() async throws {
        MockURLProtocol.addGate(for: "/api/watch/4.1/start")
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec_stale\",\"session_id\":\"watch_stale\",\"title\":\"NBC\",\"play_url\":\"/stream/4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/5.1/start"] = (
            Data("{\"recording_id\":\"rec_new\",\"session_id\":\"watch_new\",\"title\":\"CBS\",\"play_url\":\"/stream/5.1\"}".utf8), 200
        )
        // `/api/dvr/recording-stream-hls` is a single fixed path for every
        // session - queue responses in the order the two negotiations are
        // expected to actually reach it: the ungated second call first, then
        // the gated first call once its gate is released below.
        MockURLProtocol.enqueueResponse(
            Data("{\"session_id\":\"hls_new\",\"playlist_url\":\"/api/streaming/hls/hls_new/playlist.m3u8\"}".utf8),
            status: 200, for: "/api/dvr/recording-stream-hls"
        )
        MockURLProtocol.enqueueResponse(
            Data("{\"session_id\":\"hls_stale\",\"playlist_url\":\"/api/streaming/hls/hls_stale/playlist.m3u8\"}".utf8),
            status: 200, for: "/api/dvr/recording-stream-hls"
        )
        MockURLProtocol.handlers["/api/watch/watch_stale/stop"] = (Data("{}".utf8), 200)
        MockURLProtocol.handlers["/api/hls/hls_stale/stop"] = (Data("{}".utf8), 200)

        let vm = makeMockedViewModel()
        let staleTask = Task { await vm.playChannel(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC")) }

        // Give the stale call time to clear `closePlayer()` and reach the
        // gated negotiation call before the superseding call starts.
        try await Task.sleep(nanoseconds: 100_000_000)
        await vm.playChannel(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))

        XCTAssertEqual(vm.activeChannel?.channelNumber, "5.1")
        XCTAssertEqual(vm.activeHLSSessionId, "hls_new")

        MockURLProtocol.releaseGate(for: "/api/watch/4.1/start")
        await staleTask.value

        // The superseding call's result must survive untouched.
        XCTAssertEqual(vm.activeChannel?.channelNumber, "5.1")
        XCTAssertEqual(vm.activeHLSSessionId, "hls_new")

        // Teardown of the stale negotiation's session is fire-and-forget
        // (`runWithBackgroundGrace`), so poll briefly rather than asserting
        // immediately after `staleTask` resolves.
        for _ in 0..<25 where !(
            MockURLProtocol.requestLog.contains("/api/hls/hls_stale/stop")
                && MockURLProtocol.requestLog.contains("/api/watch/watch_stale/stop")
        ) {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/hls/hls_stale/stop"), "Expected the superseded negotiation's HLS session to be stopped")
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/watch/watch_stale/stop"), "Expected the superseded negotiation's watch session to be stopped")
    }

    /// `loadRecordingMetadata`'s fetch used to be a bare fire-and-forget
    /// `Task` with no stored handle, so it could complete after
    /// `closePlayer()` and repopulate `playerEngine.duration` (via
    /// `onMetadataDetail`) on an already-reset engine. Gate the metadata
    /// fetch so `closePlayer()` is guaranteed to land while it's in flight.
    func testClosePlayerDuringMetadataFetchDoesNotApplyStaleDetail() async throws {
        MockURLProtocol.addGate(for: "/api/dvr/recording-detail")
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\": \"sess-1\", \"playlist_url\": \"/api/hls/sess-1/playlist.m3u8\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-detail"] = (
            Data(
                "{\"is_in_progress\": false, \"duration_seconds\": 300.0, \"video\": {\"codec\": \"h264\"}, \"audio\": [], \"has_captions\": false, \"transcode\": {\"transcoding\": false, \"hardware\": false}}"
                    .utf8
            ), 200
        )

        let vm = makeMockedViewModel()
        let recording = HDHomeRunRecording(recordingId: "rec-1", title: "A Recording", playUrl: "http://hdhr/rec.mpg")
        let playTask = Task { await vm.playRecording(recording) }

        // Give `playRecording` time to negotiate the HLS session and reach
        // the gated metadata fetch before closing the player out from under it.
        try await Task.sleep(nanoseconds: 100_000_000)
        vm.closePlayer()
        XCTAssertEqual(vm.playerEngine.duration, 0.0, accuracy: 0.01)

        MockURLProtocol.releaseGate(for: "/api/dvr/recording-detail")
        await playTask.value

        // Give the (cancelled) metadata task a moment to have wrongly applied
        // the stale detail if the cancellation guard weren't in place.
        try await Task.sleep(nanoseconds: 150_000_000)
        XCTAssertEqual(vm.playerEngine.duration, 0.0, accuracy: 0.01, "Stale recording metadata must not repopulate a closed player")
    }
}
