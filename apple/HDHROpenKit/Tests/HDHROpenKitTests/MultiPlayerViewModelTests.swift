import XCTest
@testable import HDHROpenKit

@MainActor
final class MultiPlayerViewModelTests: XCTestCase {
    private func makeAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
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
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")
        setupMockFeed(channelNumber: "9.1", sessId: "sess4")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

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
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")
        setupMockFeed(channelNumber: "9.1", sessId: "sess4")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

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
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

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

        // Switch audio to slot 2 (ABC)
        vm.setAudioSlot(index: 2)
        XCTAssertEqual(vm.activeSlotIndex, 2)
        XCTAssertTrue(vm.slots[0].isMuted)
        XCTAssertTrue(vm.slots[1].isMuted)
        XCTAssertFalse(vm.slots[2].isMuted)
        XCTAssertFalse(vm.slots[2].playerEngine.isMuted)
    }

    // MARK: - Tile Swapping

    func testSwapSlotsReordersAndPreservesAudioFocus() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

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
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")

        let client = makeAPIClient()
        let watchManager = WatchSessionManager(apiClient: client)
        let vm = MultiPlayerViewModel(apiClient: client, watchSessionManager: watchManager)

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

        try await vm.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))

        XCTAssertEqual(vm.slots.count, 1)
        XCTAssertNotNil(vm.slots[0].warningMessage)
        XCTAssertTrue(vm.slots[0].warningMessage?.contains("Physical tuners exhausted") == true)
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
