import XCTest
@testable import HDHROpenKit

/// `PlaybackPreferences` persists `videoQuality` to `UserDefaults.standard`
/// (mirrored from the private key in PlaybackPreferences.swift) and every
/// `PlayerViewModel` constructs its own instance that reads this key at
/// init, so a `selectQuality` call in one test leaks into the next test's
/// fresh view model unless reset - same pitfall `ThemeManagerTests` guards
/// against for `themeMode`.
private let videoQualityDefaultsKey = "org.hdhropen.client.videoQuality"

@MainActor
final class PlayerViewModelQualityTests: XCTestCase {
    private var savedDefaultsValue: String?

    override func setUp() {
        super.setUp()
        savedDefaultsValue = UserDefaults.standard.string(forKey: videoQualityDefaultsKey)
        UserDefaults.standard.removeObject(forKey: videoQualityDefaultsKey)
    }

    override func tearDown() {
        if let savedDefaultsValue {
            UserDefaults.standard.set(savedDefaultsValue, forKey: videoQualityDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: videoQualityDefaultsKey)
        }
        MockURLProtocol.handlers = [:]
        MockURLProtocol.resetLog()
        super.tearDown()
    }

    private func makeMockedViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        return PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
    }

    // MARK: - selectQuality no-op

    func testSelectQualityIsNoOpWhenAlreadyAtRequestedPreference() async {
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
        XCTAssertEqual(vm.quality, .auto)

        MockURLProtocol.resetLog()
        await vm.selectQuality(.auto)

        XCTAssertEqual(vm.activeHLSSessionId, "sess-1")
        XCTAssertTrue(MockURLProtocol.requestLog.isEmpty, "Expected no new session request for a no-op quality selection")
    }

    // MARK: - selectQuality switches session

    func testSelectQualitySwitchesSessionForActiveChannelAndStopsOldOne() async {
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

        await vm.selectQuality(.low)

        XCTAssertEqual(vm.activeHLSSessionId, "sess-2")
        XCTAssertEqual(vm.quality, .low)
        XCTAssertFalse(vm.isSwitchingQuality)

        try? await MockURLProtocol.waitUntilLogged("/api/hls/sess-1/stop")
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/hls/sess-1/stop"), "Expected the superseded session to be stopped")
    }

    // MARK: - selectQuality on a recording

    func testSelectQualitySwitchesSessionForActiveRecording() async {
        let vm = makeMockedViewModel()
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\": \"sess-1\", \"playlist_url\": \"/api/hls/sess-1/playlist.m3u8\"}".utf8), 200
        )
        let recording = HDHomeRunRecording(recordingId: "rec-1", title: "A Recording", playUrl: "http://hdhr/rec.mpg")
        await vm.playRecording(recording)
        XCTAssertEqual(vm.activeHLSSessionId, "sess-1")

        await vm.selectQuality(.medium)

        // Same handler path serves both the initial negotiation and the
        // quality-switch call (per-path matching, not per-session), so this
        // exercises the recording branch of `switchToQuality` without
        // needing a second stub - mirroring
        // `testSelectAudioTrackSwitchesSessionForActiveRecording`.
        XCTAssertEqual(vm.activeHLSSessionId, "sess-1")
        XCTAssertEqual(vm.quality, .medium)
    }

    // MARK: - Auto poll: downgrade requires buffer drain, not just low throughput

    func testAutoPollDowngradesOnLowThroughputWithDrainingBuffer() async {
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
        XCTAssertEqual(vm.autoEffectiveTier, .high)

        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (
            Data("{\"session_id\": \"sess-2\", \"playlist_url\": \"/api/hls/sess-2/playlist.m3u8\", \"title\": \"Test Channel\"}".utf8), 200
        )

        // Seed a healthy baseline near the .high target, then a sustained
        // drop plus a draining buffer (shrinking, below the safe floor).
        vm.speedSamplesMbps = Array(repeating: 5.0, count: 24)
        vm.bufferedAheadSamples = [20.0, 14.0, 9.0, 4.0]
        vm.playerEngine.observedBitrate = 2_000_000 // 2 Mbps

        for _ in 0..<3 {
            vm.speedSamplesMbps.append(2.0)
            if vm.speedSamplesMbps.count > 24 {
                vm.speedSamplesMbps.removeFirst()
            }
            await vm.sampleAutoQualityTick()
        }

        XCTAssertNotEqual(vm.autoEffectiveTier, .high, "Expected a downgrade once throughput drops with a draining buffer")
        XCTAssertEqual(vm.activeHLSSessionId, "sess-2")

        try? await MockURLProtocol.waitUntilLogged("/api/hls/sess-1/stop")
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/hls/sess-1/stop"), "Expected the pre-downgrade session to be stopped")
    }

    // MARK: - Auto poll: no downgrade when buffer stays healthy

    func testAutoPollDoesNotDowngradeOnLowThroughputWithHealthyBuffer() async {
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
        XCTAssertEqual(vm.autoEffectiveTier, .high)

        // A second handler registered here would reveal an unwanted switch -
        // intentionally omitted so any erroneous request 404s and the
        // assertion below catches it via the unchanged session id.
        MockURLProtocol.resetLog()

        vm.speedSamplesMbps = Array(repeating: 5.0, count: 24)
        vm.playerEngine.observedBitrate = 2_000_000 // 2 Mbps

        // `bufferedAheadSeconds()` reads the real (unmocked) `AVPlayerItem`
        // in this test environment, which has no actual loaded time ranges
        // and so always reports a constant 0 - deliberately left unseeded
        // here (unlike the draining test above) so `bufferedAheadSamples`
        // fills with that same flat, non-dropping value every tick.
        // `isBufferDraining()` requires an actual drop across the window,
        // not merely a low absolute floor, so a flat trend - even a flat-low
        // one - never reads as draining. These priming ticks (healthy
        // throughput) just let the window fill before the real assertion.
        for _ in 0..<4 {
            await vm.sampleAutoQualityTick()
        }
        XCTAssertEqual(vm.autoEffectiveTier, .high, "Priming ticks with healthy throughput should not have triggered a downgrade")

        for _ in 0..<3 {
            vm.speedSamplesMbps.append(2.0)
            if vm.speedSamplesMbps.count > 24 {
                vm.speedSamplesMbps.removeFirst()
            }
            await vm.sampleAutoQualityTick()
        }

        XCTAssertEqual(vm.autoEffectiveTier, .high, "Expected no downgrade on low throughput once the buffer trend is flat (non-draining)")
        XCTAssertEqual(vm.activeHLSSessionId, "sess-1")
        XCTAssertFalse(MockURLProtocol.requestLog.contains("/api/streaming/hls/4.1"), "Expected no new session request")
    }
}
