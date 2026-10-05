import XCTest
@testable import HDHROpenKit

/// Covers the auto-skip-commercials preference's Combine-driven guard in
/// `PlayerViewModel.init` (`CombineLatest` on `playerEngine.$currentTime` /
/// `$commercialSegments`), mirroring Android's equivalent additions to
/// `PlayerViewModelSeekResyncTest.kt`. Like that file, these tests exploit
/// the fact that a `PlayerEngine` loaded against a fake URL in a unit test
/// never gets real buffered `seekableTimeRanges`, so `isPositionInSeekableRange`
/// is always `false` and any `PlayerViewModel.seek(to:)` call with a non-nil
/// `activeRecording` deterministically routes through `seekRecordingViaServer`.
@MainActor
final class PlayerViewModelAutoSkipCommercialTests: XCTestCase {
    private func makeMockedViewModel(autoSkipEnabled: Bool) -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let prefs = PlaybackPreferences()
        prefs.autoSkipCommercialsEnabled = autoSkipEnabled
        let vm = PlayerViewModel(
            apiClient: apiClient,
            watchSessionManager: WatchSessionManager(apiClient: apiClient),
            playbackPreferences: prefs
        )
        vm.playerEngine.loadMedia(url: URL(string: "http://localhost:8000/fake.m3u8")!, isSeekable: true)
        return vm
    }

    private func recording() -> HDHomeRunRecording {
        HDHomeRunRecording(recordingId: "rec-1", title: "A Recording", playUrl: "http://hdhr/rec.mpg")
    }

    private func hlsSessionResponse(sessionId: String) -> Data {
        Data("{\"session_id\":\"\(sessionId)\",\"playlist_url\":\"/api/streaming/hls/\(sessionId)/playlist.m3u8\"}".utf8)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        MockURLProtocol.resetLog()
        MockURLProtocol.resetGates()
        MockURLProtocol.resetQueues()
        super.tearDown()
    }

    func testAutoSkipSeeksPastTheActiveCommercialSegmentWhenThePreferenceIsEnabled() async throws {
        let vm = makeMockedViewModel(autoSkipEnabled: true)
        vm.activeRecording = recording()
        vm.playerEngine.setCommercialSegments([HDHomeRunCommercialSegment(startSeconds: 10, endSeconds: 40)])
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (hlsSessionResponse(sessionId: "hls-1"), 200)

        // Stands in for playback naturally reaching the segment.
        vm.playerEngine.seek(to: 15)

        try await MockURLProtocol.waitUntilLogged("/api/dvr/recording-stream-hls")
        try await Task.sleep(nanoseconds: 100_000_000)

        XCTAssertEqual(vm.activeHLSSessionId, "hls-1")
        XCTAssertEqual(vm.playerEngine.currentTime, 40, accuracy: 0.01)
        XCTAssertNotNil(vm.autoSkipPulse)
    }

    func testNoAutoSkipOccursWhenThePreferenceIsDisabled() async throws {
        let vm = makeMockedViewModel(autoSkipEnabled: false)
        vm.activeRecording = recording()
        vm.playerEngine.setCommercialSegments([HDHomeRunCommercialSegment(startSeconds: 10, endSeconds: 40)])

        vm.playerEngine.seek(to: 15)
        try await Task.sleep(nanoseconds: 100_000_000)

        XCTAssertEqual(vm.playerEngine.currentTime, 15, accuracy: 0.01)
        XCTAssertTrue(MockURLProtocol.requestLog.isEmpty, "Disabled preference must never trigger a server seek")
        XCTAssertNil(vm.autoSkipPulse)
    }

    func testAutoSkipFiresAtMostOncePerSegmentEvenIfPlaybackReEntersIt() async throws {
        let vm = makeMockedViewModel(autoSkipEnabled: true)
        vm.activeRecording = recording()
        vm.playerEngine.setCommercialSegments([HDHomeRunCommercialSegment(startSeconds: 10, endSeconds: 40)])
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (hlsSessionResponse(sessionId: "hls-1"), 200)

        vm.playerEngine.seek(to: 15)
        try await MockURLProtocol.waitUntilLogged("/api/dvr/recording-stream-hls")
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertEqual(MockURLProtocol.requestLog.filter { $0 == "/api/dvr/recording-stream-hls" }.count, 1)

        // Playback re-enters the same segment (e.g. the server-seek landed
        // slightly before the segment's end).
        vm.playerEngine.seek(to: 12)
        try await Task.sleep(nanoseconds: 100_000_000)

        XCTAssertEqual(
            MockURLProtocol.requestLog.filter { $0 == "/api/dvr/recording-stream-hls" }.count, 1,
            "Must not auto-skip the same segment a second time"
        )
    }

    func testAutoSkipGuardSurvivesSeekRecordingViaServersSegmentListRestoreWithoutDoubleSkipping() async throws {
        let vm = makeMockedViewModel(autoSkipEnabled: true)
        vm.activeRecording = recording()
        vm.playerEngine.setCommercialSegments([HDHomeRunCommercialSegment(startSeconds: 10, endSeconds: 40)])
        MockURLProtocol.enqueueResponse(hlsSessionResponse(sessionId: "hls-1"), status: 200, for: "/api/dvr/recording-stream-hls")
        MockURLProtocol.enqueueResponse(hlsSessionResponse(sessionId: "hls-2"), status: 200, for: "/api/dvr/recording-stream-hls")

        // Playback reaches the segment - fires the one and only auto-skip.
        vm.playerEngine.seek(to: 15)
        try await MockURLProtocol.waitUntilLogged("/api/dvr/recording-stream-hls")
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertEqual(MockURLProtocol.requestLog.filter { $0 == "/api/dvr/recording-stream-hls" }.count, 1)
        XCTAssertFalse(vm.playerEngine.commercialSegments.isEmpty, "Segments must survive the auto-skip's own server-seek reload")

        // A second, user-initiated seek back into the same segment must still
        // reach the server normally (e.g. the viewer scrubs backward past the
        // buffered range) - and must still restore the segment list - without
        // the restore re-triggering a second auto-skip.
        vm.seek(to: 12)
        try await Task.sleep(nanoseconds: 150_000_000)

        XCTAssertEqual(
            MockURLProtocol.requestLog.filter { $0 == "/api/dvr/recording-stream-hls" }.count, 2,
            "The second, user-initiated seek must still reach the server"
        )
        XCTAssertFalse(vm.playerEngine.commercialSegments.isEmpty, "Segments must survive the second reload too")
        XCTAssertEqual(vm.playerEngine.currentTime, 12, accuracy: 0.01, "Guard must not re-fire a second auto-skip for the same segment")
    }

    func testAutoSkipGuardResetsOnClosePlayerSoANewRecordingCanAutoSkipAtTheSameSegmentStart() async throws {
        let vm = makeMockedViewModel(autoSkipEnabled: true)
        vm.activeRecording = recording()
        vm.playerEngine.setCommercialSegments([HDHomeRunCommercialSegment(startSeconds: 10, endSeconds: 40)])
        MockURLProtocol.enqueueResponse(hlsSessionResponse(sessionId: "hls-1"), status: 200, for: "/api/dvr/recording-stream-hls")

        vm.playerEngine.seek(to: 15)
        try await MockURLProtocol.waitUntilLogged("/api/dvr/recording-stream-hls")
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertEqual(MockURLProtocol.requestLog.filter { $0 == "/api/dvr/recording-stream-hls" }.count, 1)

        vm.closePlayer()

        // A genuinely new recording, loaded fresh, with a commercial segment
        // starting at the exact same offset as before.
        vm.activeRecording = recording()
        vm.playerEngine.loadMedia(url: URL(string: "http://localhost:8000/fake2.m3u8")!, isSeekable: true)
        vm.playerEngine.setCommercialSegments([HDHomeRunCommercialSegment(startSeconds: 10, endSeconds: 40)])
        MockURLProtocol.enqueueResponse(hlsSessionResponse(sessionId: "hls-2"), status: 200, for: "/api/dvr/recording-stream-hls")

        vm.playerEngine.seek(to: 15)
        try await Task.sleep(nanoseconds: 150_000_000)

        XCTAssertEqual(
            MockURLProtocol.requestLog.filter { $0 == "/api/dvr/recording-stream-hls" }.count, 2,
            "A new recording must be able to auto-skip the same segment start again"
        )
    }
}
