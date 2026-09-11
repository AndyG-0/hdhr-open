import XCTest
@testable import HDHROpenKit

@MainActor
final class MultiPlayerViewModelTests: XCTestCase {
    private func makeAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        MockURLProtocol.resetLog()
        MockURLProtocol.resetGates()
        MockURLProtocol.resetQueues()
        super.tearDown()
    }

    private func setupMockFeed(channelNumber: String, sessId: String) {
        MockURLProtocol.handlers["/api/watch/\(channelNumber)/start"] = (
            Data(
                "{\"recording_id\":\"rec_\(sessId)\",\"session_id\":\"\(sessId)\",\"title\":\"Channel \(channelNumber)\",\"play_url\":\"/stream/\(channelNumber)\"}"
                    .utf8
            ), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\":\"hls_\(sessId)\",\"playlist_url\":\"/api/streaming/hls/hls_\(sessId)/playlist.m3u8\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/\(sessId)/stop"] = (Data("{}".utf8), 200)
        MockURLProtocol.handlers["/api/hls/hls_\(sessId)/stop"] = (Data("{}".utf8), 200)
    }

    private func setupMockTunerInfo(count: Int) {
        MockURLProtocol.handlers["/api/tuner/info"] = (
            Data("{\"friendly_name\":\"HDHomeRun CONNECT\",\"model_number\":\"HDHR4-2US\",\"tuner_count\":\(count)}".utf8),
            200
        )
    }

    // MARK: - Tuner Capacity & Limits

    func test2TunerLimitEnforcesMax2FeedsAndSideBySideLayoutOnly() async throws {
        setupMockTunerInfo(count: 2)
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)
        await vm.refreshTunerCapacity()

        XCTAssertEqual(vm.totalTuners, 2)
        XCTAssertEqual(vm.maxFeeds, 2)
        XCTAssertEqual(MultiViewLayout.availableLayouts(for: vm.maxFeeds), [.sideBySide])

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))

        XCTAssertEqual(vm.slots.count, 2)
        XCTAssertFalse(vm.canAddFeed)

        do {
            try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))
            XCTFail("Expected adding 3rd feed on 2-tuner setup to throw maxSlotsReached")
        } catch let error as MultiViewError {
            XCTAssertEqual(error, .maxSlotsReached)
        }
    }

    func test4TunerAllowsUpTo4FeedsAndFullLayouts() async throws {
        setupMockTunerInfo(count: 4)
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")
        setupMockFeed(channelNumber: "9.1", sessId: "sess4")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)
        await vm.refreshTunerCapacity()

        XCTAssertEqual(vm.totalTuners, 4)
        XCTAssertEqual(vm.maxFeeds, 4)
        XCTAssertEqual(MultiViewLayout.availableLayouts(for: vm.maxFeeds), [.sideBySide, .threeBox, .quad])

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        XCTAssertEqual(vm.layout, .sideBySide)
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        XCTAssertEqual(vm.layout, .sideBySide)
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))
        XCTAssertEqual(vm.layout, .threeBox)
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "9.1", name: "FOX"))
        XCTAssertEqual(vm.layout, .quad)

        XCTAssertEqual(vm.slots.count, 4)
        XCTAssertFalse(vm.canAddFeed)
    }

    func testTunerSharingAllowsChannelActiveOnRecordingEvenWhenAllTunersInUse() async throws {
        setupMockTunerInfo(count: 2)
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")

        // Tuner 0 is recording Ch 4.1 "Evening News", Tuner 1 is in use for live TV Ch 5.1
        let tunerJson = """
        [
            {
                "index": 0,
                "in_use": true,
                "channel_number": "4.1",
                "channel_name": "NBC",
                "client": {
                    "type": "scheduled_recording",
                    "name": "Evening News",
                    "is_recording": true,
                    "recording_id": "rec_news_123",
                    "viewers": []
                }
            },
            {
                "index": 1,
                "in_use": true,
                "channel_number": "5.1",
                "channel_name": "CBS",
                "client": {
                    "type": "live",
                    "name": "Living Room Apple TV",
                    "is_recording": false,
                    "viewers": []
                }
            }
        ]
        """
        MockURLProtocol.handlers["/api/tuner/status"] = (Data(tunerJson.utf8), 200)

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)
        await vm.refreshTunerCapacity()

        // 1. Tuning Ch 4.1 (active recording) must succeed via tuner sharing!
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        XCTAssertEqual(vm.slots.count, 1)
        XCTAssertEqual(vm.slots[0].channel.channelNumber, "4.1")

        // 2. Tuning a distinct channel Ch 7.1 must fail with tuner exhaustion explanation
        do {
            try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))
            XCTFail("Expected adding distinct channel Ch 7.1 to fail with tunerUnavailable")
        } catch let error as MultiViewError {
            if case let .tunerUnavailable(msg) = error {
                XCTAssertTrue(msg.contains("All 2 tuners are currently in use"))
                XCTAssertTrue(msg.contains("1 recording: Evening News (Ch 4.1)"))
                XCTAssertTrue(msg.contains("1 streaming: Ch 5.1 (Living Room Apple TV)"))
                XCTAssertTrue(msg.contains("You can watch Ch 4.1 without consuming another tuner"))
            } else {
                XCTFail("Unexpected error: \(error)")
            }
        }
    }

    func testAvailableLayoutsHelper() {
        XCTAssertEqual(MultiViewLayout.availableLayouts(for: 1), [.sideBySide])
        XCTAssertEqual(MultiViewLayout.availableLayouts(for: 2), [.sideBySide])
        XCTAssertEqual(MultiViewLayout.availableLayouts(for: 3), [.sideBySide, .threeBox])
        XCTAssertEqual(MultiViewLayout.availableLayouts(for: 4), [.sideBySide, .threeBox, .quad])
    }

    // MARK: - Slot Creation & Audio Routing

    func testAddFirstFeedSetsActiveSlotAndUnmuted() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        let channel = HDHomeRunChannel(channelNumber: "4.1", name: "NBC")
        try await vm.addFeed(channel: channel)

        XCTAssertEqual(vm.slots.count, 1)
        XCTAssertEqual(vm.activeSlotIndex, 0)
        XCTAssertFalse(vm.slots[0].isMuted)
        XCTAssertFalse(vm.slots[0].playerEngine.isMuted)
        XCTAssertEqual(vm.layout, .sideBySide)
        XCTAssertTrue(vm.isMultiViewActive)
        XCTAssertEqual(vm.activeSlot?.channel.channelNumber, "4.1")
    }

    func testAddMultipleFeedsMutesSubsequentSlotsAndPreservesPrimaryAudio() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))

        XCTAssertEqual(vm.slots.count, 2)
        XCTAssertEqual(vm.activeSlotIndex, 0)

        // Slot 0 (primary) remains unmuted
        XCTAssertFalse(vm.slots[0].isMuted)
        XCTAssertFalse(vm.slots[0].playerEngine.isMuted)

        // Slot 1 (subsequent) is muted
        XCTAssertTrue(vm.slots[1].isMuted)
        XCTAssertTrue(vm.slots[1].playerEngine.isMuted)
    }

    func testAddFeedBeyondMaxLimitThrowsMaxSlotsReached() async throws {
        setupMockTunerInfo(count: 4)
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")
        setupMockFeed(channelNumber: "9.1", sessId: "sess4")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)
        await vm.refreshTunerCapacity()

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "9.1", name: "FOX"))

        XCTAssertEqual(vm.slots.count, 4)
        XCTAssertFalse(vm.canAddFeed)

        do {
            try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "11.1", name: "CW"))
            XCTFail("Expected addFeed to throw MultiViewError.maxSlotsReached")
        } catch let error as MultiViewError {
            XCTAssertEqual(error, .maxSlotsReached)
        }

        XCTAssertEqual(vm.slots.count, 4)
    }

    // MARK: - Auto Layout Transitions

    func testAutoLayoutTransitions() async throws {
        setupMockTunerInfo(count: 4)
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")
        setupMockFeed(channelNumber: "9.1", sessId: "sess4")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)
        await vm.refreshTunerCapacity()

        // 1-2 feeds: sideBySide
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        XCTAssertEqual(vm.layout, .sideBySide)
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        XCTAssertEqual(vm.layout, .sideBySide)

        // 3 feeds: threeBox
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))
        XCTAssertEqual(vm.layout, .threeBox)

        // 4 feeds: quad
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "9.1", name: "FOX"))
        XCTAssertEqual(vm.layout, .quad)

        // Remove 1 feed (down to 3): threeBox
        vm.removeFeed(at: 3)
        XCTAssertEqual(vm.layout, .threeBox)

        // Remove 1 feed (down to 2): sideBySide
        vm.removeFeed(at: 2)
        XCTAssertEqual(vm.layout, .sideBySide)
    }

    // MARK: - Audio Routing & Focus Engine

    func testSetAudioSlotSwitchesFocusAndMutesOthers() async throws {
        setupMockTunerInfo(count: 4)
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)
        await vm.refreshTunerCapacity()

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))

        // Switch audio to slot 1 (CBS)
        vm.setAudioSlot(index: 1)
        XCTAssertEqual(vm.activeSlotIndex, 1)
        XCTAssertTrue(vm.slots[0].isMuted)
        XCTAssertFalse(vm.slots[1].isMuted)
        XCTAssertFalse(vm.slots[1].playerEngine.isMuted)
        XCTAssertTrue(vm.slots[2].isMuted)

        // REV-APL-15: the audio-focused slot's decode bitrate is uncapped;
        // every other slot is capped rather than paused, since multi-view's
        // whole premise is every tile staying visibly live.
        XCTAssertGreaterThan(vm.slots[0].playerEngine.preferredPeakBitRate, 0)
        XCTAssertEqual(vm.slots[1].playerEngine.preferredPeakBitRate, 0)
        XCTAssertGreaterThan(vm.slots[2].playerEngine.preferredPeakBitRate, 0)

        // Switch audio to slot 2 (ABC)
        vm.setAudioSlot(index: 2)
        XCTAssertEqual(vm.activeSlotIndex, 2)
        XCTAssertTrue(vm.slots[0].isMuted)
        XCTAssertTrue(vm.slots[1].isMuted)
        XCTAssertFalse(vm.slots[2].isMuted)
        XCTAssertFalse(vm.slots[2].playerEngine.isMuted)

        XCTAssertGreaterThan(vm.slots[0].playerEngine.preferredPeakBitRate, 0)
        XCTAssertGreaterThan(vm.slots[1].playerEngine.preferredPeakBitRate, 0)
        XCTAssertEqual(vm.slots[2].playerEngine.preferredPeakBitRate, 0)
    }

    // MARK: - Tile Swapping

    func testSwapSlotsReordersAndPreservesAudioFocus() async throws {
        setupMockTunerInfo(count: 4)
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)
        await vm.refreshTunerCapacity()

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))

        // Currently slot 0 is focused (NBC)
        XCTAssertEqual(vm.activeSlotIndex, 0)

        // Swap slot 0 (NBC) and slot 2 (ABC)
        vm.swapSlots(from: 0, to: 2)

        // Slot 0 is now ABC, Slot 2 is NBC
        XCTAssertEqual(vm.slots[0].channel.channelNumber, "7.1")
        XCTAssertEqual(vm.slots[2].channel.channelNumber, "4.1")

        // Audio focus should follow the moved stream (now at index 2)
        XCTAssertEqual(vm.activeSlotIndex, 2)
        XCTAssertTrue(vm.slots[0].isMuted)
        XCTAssertTrue(vm.slots[1].isMuted)
        XCTAssertFalse(vm.slots[2].isMuted)
        XCTAssertFalse(vm.slots[2].playerEngine.isMuted)
    }

    // MARK: - Slot Removal & Teardown

    func testRemoveActiveAudioSlotSelectsNewActiveSlotGracefully() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))

        // Focus slot 1 (CBS)
        vm.setAudioSlot(index: 1)
        XCTAssertEqual(vm.activeSlotIndex, 1)

        // Remove slot 1
        vm.removeFeed(at: 1)

        XCTAssertEqual(vm.slots.count, 1)
        XCTAssertEqual(vm.activeSlotIndex, 0)
        XCTAssertFalse(vm.slots[0].isMuted)
        XCTAssertFalse(vm.slots[0].playerEngine.isMuted)
    }

    func testRemoveSlotBeforeActiveAudioSlotShiftsIndex() async throws {
        setupMockTunerInfo(count: 4)
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)
        await vm.refreshTunerCapacity()

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))

        // Focus slot 2 (ABC)
        vm.setAudioSlot(index: 2)
        XCTAssertEqual(vm.activeSlotIndex, 2)

        // Remove slot 0 (NBC)
        vm.removeFeed(at: 0)

        // Remaining: slot 0 (CBS), slot 1 (ABC)
        XCTAssertEqual(vm.slots.count, 2)
        XCTAssertEqual(vm.activeSlotIndex, 1)
        XCTAssertEqual(vm.slots[1].channel.channelNumber, "7.1")
        XCTAssertFalse(vm.slots[1].isMuted)
    }

    // MARK: - Tuner Exhaustion & Direct HLS Fallback

    func testPhysicalTunerExhaustionAttachesWarningToSlot() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")

        // Mock tuner status returning 2 tuners, both in use
        let tunerJson = """
        [
            {"index": 0, "in_use": true, "channel_number": "2.1"},
            {"index": 1, "in_use": true, "channel_number": "3.1"}
        ]
        """
        MockURLProtocol.handlers["/api/tuner/status"] = (Data(tunerJson.utf8), 200)

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        do {
            try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
            XCTFail("Expected addFeed to throw tunerUnavailable error")
        } catch let error as MultiViewError {
            if case let .tunerUnavailable(msg) = error {
                XCTAssertTrue(msg.contains("All 2 tuners are currently in use"))
                XCTAssertTrue(msg.contains("Close an active feed"))
            } else {
                XCTFail("Unexpected error: \(error)")
            }
        }

        XCTAssertEqual(vm.slots.count, 1)
        XCTAssertNotNil(vm.slots[0].warningMessage)
        XCTAssertTrue(vm.slots[0].warningMessage?.contains("All 2 tuners are currently in use") == true)
        if case let .failed(msg) = vm.slots[0].playerEngine.state {
            XCTAssertTrue(msg.contains("All 2 tuners are currently in use"))
        } else {
            XCTFail("Expected playerEngine.state to be .failed")
        }
    }

    func testFallbackToDirectHLSWhenWatchSessionFails() async throws {
        // Watch start fails (e.g. 503 no free tuner for watch session)
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (Data("{}".utf8), 503)

        // Direct channel HLS stream succeeds
        MockURLProtocol.handlers["/api/streaming/hls/4.1"] = (
            Data("{\"session_id\":\"direct_hls_sess_1\",\"title\":\"Direct NBC\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/hls/direct_hls_sess_1/stop"] = (Data("{}".utf8), 200)

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))

        XCTAssertEqual(vm.slots.count, 1)
        XCTAssertEqual(vm.slots[0].hlsSessionId, "direct_hls_sess_1")
        XCTAssertNil(vm.slots[0].watchRecording)
    }

    // MARK: - Replace Feed & Close All

    func testReplaceFeedInPlace() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        XCTAssertEqual(vm.slots[0].channel.channelNumber, "4.1")

        try await vm.replaceFeed(at: 0, with: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        XCTAssertEqual(vm.slots[0].channel.channelNumber, "5.1")
        XCTAssertEqual(vm.slots[0].channel.name, "CBS")
        XCTAssertEqual(vm.slots[0].hlsSessionId, "hls_sess2")
    }

    /// A second `replaceFeed(at:)` targeting the same slot while the first
    /// is still negotiating must win outright: the first call's result has
    /// to be discarded (never overwriting the second's) and its
    /// now-orphaned session torn down. Uses `MockURLProtocol`'s gate
    /// mechanism to land the second call deterministically mid-negotiation
    /// of the first, rather than racing on timing.
    func testReplaceFeedIsNoOpIfSlotWasReplacedAgainWhileInFlight() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        XCTAssertEqual(vm.slots[0].hlsSessionId, "hls_sess1")

        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")
        MockURLProtocol.addGate(for: "/api/watch/5.1/start")

        // `/api/dvr/recording-stream-hls` is one fixed path shared by every
        // session negotiation - plain `handlers[path] =` entries for two
        // different sessions on it just clobber each other, which is fine
        // when only one negotiation is in flight at a time but not here.
        // Queue the two responses explicitly, in the order the requests are
        // expected to actually arrive: the second replace (7.1) runs
        // ungated and reaches this endpoint first; the stale replace (5.1)
        // only reaches it after its gate is released below.
        MockURLProtocol.enqueueResponse(
            Data("{\"session_id\":\"hls_sess3\",\"playlist_url\":\"/api/streaming/hls/hls_sess3/playlist.m3u8\"}".utf8),
            status: 200, for: "/api/dvr/recording-stream-hls"
        )
        MockURLProtocol.enqueueResponse(
            Data("{\"session_id\":\"hls_sess2\",\"playlist_url\":\"/api/streaming/hls/hls_sess2/playlist.m3u8\"}".utf8),
            status: 200, for: "/api/dvr/recording-stream-hls"
        )

        let staleTask = Task {
            try await vm.replaceFeed(at: 0, with: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        }

        // Wait for the stale replace to clear its tuner-availability check
        // and reach the gated negotiation call before the second replace
        // targets the same slot.
        try await MockURLProtocol.waitUntilLogged("/api/watch/5.1/start")
        try await vm.replaceFeed(at: 0, with: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))

        XCTAssertEqual(vm.slots[0].channel.channelNumber, "7.1")
        XCTAssertEqual(vm.slots[0].hlsSessionId, "hls_sess3")

        MockURLProtocol.releaseGate(for: "/api/watch/5.1/start")
        try await staleTask.value

        // The second replace's result must survive untouched.
        XCTAssertEqual(vm.slots[0].channel.channelNumber, "7.1")
        XCTAssertEqual(vm.slots[0].hlsSessionId, "hls_sess3")

        for _ in 0..<25 where !(
            MockURLProtocol.requestLog.contains("/api/hls/hls_sess2/stop")
                && MockURLProtocol.requestLog.contains("/api/watch/sess2/stop")
        ) {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/hls/hls_sess2/stop"), "Expected the stale replace's orphaned HLS session to be stopped")
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/watch/sess2/stop"), "Expected the stale replace's orphaned watch session to be stopped")
    }

    func testCloseAllTearsDownEverything() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        XCTAssertEqual(vm.slots.count, 2)

        vm.closeAll()

        XCTAssertTrue(vm.slots.isEmpty)
        XCTAssertEqual(vm.activeSlotIndex, 0)
        XCTAssertFalse(vm.isMultiViewActive)
    }

    // MARK: - Instant Slot Reservation (tvOS multi-view Fix 1)

    /// `beginAddFeed` must append a `.loading` slot synchronously, with no network mock
    /// registered - if this were still doing negotiation inline (the old `addFeed` behavior),
    /// there'd be nothing to await and no slot would exist yet.
    func testBeginAddFeedReservesLoadingSlotSynchronously() throws {
        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        let channel = HDHomeRunChannel(channelNumber: "4.1", name: "NBC")
        let slotId = try vm.beginAddFeed(channel: channel)

        XCTAssertEqual(vm.slots.count, 1)
        XCTAssertEqual(vm.slots[0].id, slotId)
        XCTAssertEqual(vm.slots[0].playerEngine.state, .loading)
        XCTAssertTrue(vm.isMultiViewActive)
        XCTAssertEqual(vm.activeSlotIndex, 0)
    }

    func testFinishAddFeedPopulatesReservedSlotInPlace() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        let channel = HDHomeRunChannel(channelNumber: "4.1", name: "NBC")
        let slotId = try vm.beginAddFeed(channel: channel)
        XCTAssertNil(vm.slots[0].hlsSessionId)

        try await vm.finishAddFeed(slotId: slotId)

        XCTAssertEqual(vm.slots.count, 1)
        XCTAssertEqual(vm.slots[0].id, slotId)
        XCTAssertEqual(vm.slots[0].hlsSessionId, "hls_sess1")
    }

    func testFinishAddFeedIsNoOpIfSlotWasRemovedWhileInFlight() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        let channel = HDHomeRunChannel(channelNumber: "4.1", name: "NBC")
        let slotId = try vm.beginAddFeed(channel: channel)
        vm.removeFeed(at: 0)
        XCTAssertTrue(vm.slots.isEmpty)

        try await vm.finishAddFeed(slotId: slotId)

        XCTAssertTrue(vm.slots.isEmpty)
        // The slot was already gone before `finishAddFeed` ran, so it should
        // bail out at its very first guard, never negotiating a session in
        // the first place - nothing to tear down.
        XCTAssertFalse(MockURLProtocol.requestLog.contains("/api/watch/4.1/start"))
    }

    /// Exercises the *other* branch of the same guard: the slot is removed
    /// while a session negotiation is genuinely in flight (network call
    /// already sent), not before it starts. Uses `MockURLProtocol`'s gate
    /// mechanism to land the removal deterministically mid-negotiation
    /// rather than racing on timing, so the orphaned session's teardown can
    /// be asserted directly instead of merely inferred from `slots.isEmpty`.
    func testFinishAddFeedTearsDownNegotiatedSessionIfSlotWasRemovedWhileInFlight() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        MockURLProtocol.addGate(for: "/api/watch/4.1/start")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        let channel = HDHomeRunChannel(channelNumber: "4.1", name: "NBC")
        let slotId = try vm.beginAddFeed(channel: channel)

        let finishTask = Task { try await vm.finishAddFeed(slotId: slotId) }

        // Wait for `finishAddFeed` to clear its tuner-availability check
        // and reach the gated negotiation call before removing the slot out
        // from under it.
        try await MockURLProtocol.waitUntilLogged("/api/watch/4.1/start")
        vm.removeFeed(at: 0)
        XCTAssertTrue(vm.slots.isEmpty)

        MockURLProtocol.releaseGate(for: "/api/watch/4.1/start")
        try await finishTask.value

        XCTAssertTrue(vm.slots.isEmpty)

        // The stop calls are themselves fire-and-forget background tasks
        // (`runWithBackgroundGrace`), so poll briefly rather than asserting
        // immediately after `finishTask` resolves.
        for _ in 0..<25 where !(
            MockURLProtocol.requestLog.contains("/api/hls/hls_sess1/stop")
                && MockURLProtocol.requestLog.contains("/api/watch/sess1/stop")
        ) {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/hls/hls_sess1/stop"), "Expected the orphaned HLS session to be stopped")
        XCTAssertTrue(MockURLProtocol.requestLog.contains("/api/watch/sess1/stop"), "Expected the orphaned watch session to be stopped")
    }

    // MARK: - Expand/Collapse Background Pause-Resume (tvOS multi-view Fix 2)

    /// `PlayerEngine.pause()`/`play()` only flip `state` from `.playing`/`.buffering` or
    /// `.paused` respectively - real `.playing` requires AVPlayer to actually resolve an asset,
    /// which these offline unit tests can't produce (there's no test double for AVPlayer/
    /// AVURLAsset), so slots here stay `.loading` the whole time. That still exercises the real
    /// guard logic in `pauseBackgroundSlots`/`resumeBackgroundSlots`: it locks in that neither
    /// method force-overwrites `state` outside of those documented transitions. The actual
    /// pause-while-playing / resync-near-live-edge behavior needs on-device verification (see
    /// the plan's Verification section).
    func testPauseAndResumeBackgroundSlotsLeaveNonPlayingSlotsUntouched() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))

        vm.pauseBackgroundSlots(except: 0)
        XCTAssertEqual(vm.slots[0].playerEngine.state, .loading)
        XCTAssertEqual(vm.slots[1].playerEngine.state, .loading)

        vm.resumeBackgroundSlots()
        XCTAssertEqual(vm.slots[0].playerEngine.state, .loading)
        XCTAssertEqual(vm.slots[1].playerEngine.state, .loading)
    }
}
