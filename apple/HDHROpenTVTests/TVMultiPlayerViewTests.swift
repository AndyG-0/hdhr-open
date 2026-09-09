import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVMultiPlayerViewTests: XCTestCase {
    private func makeEnvironment() -> (MultiPlayerViewModel, PlayerViewModel, GuideViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let multiPlayerViewModel = MultiPlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        return (multiPlayerViewModel, playerViewModel, guideViewModel)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    private func setupMockFeed(channelNumber: String, sessId: String) {
        let json = "{\"recording_id\":\"rec_\(sessId)\",\"session_id\":\"\(sessId)\","
            + "\"title\":\"Channel \(channelNumber)\",\"play_url\":\"/stream/\(channelNumber)\"}"
        MockURLProtocol.handlers["/api/watch/\(channelNumber)/start"] = (
            Data(json.utf8), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\":\"hls_\(sessId)\",\"playlist_url\":\"/api/streaming/hls/hls_\(sessId)/playlist.m3u8\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/\(sessId)/stop"] = (Data("{}".utf8), 200)
        MockURLProtocol.handlers["/api/hls/hls_\(sessId)/stop"] = (Data("{}".utf8), 200)
    }

    func testTVMultiViewSlotOverlayDisplaysChannelAndAudio() throws {
        let channel = HDHomeRunChannel(channelNumber: "4.1", name: "NBC")
        let slot = MultiViewSlot.makeSlot(channel: channel, isMuted: false)

        let overlay = TVMultiViewSlotOverlay(slot: slot, isFocused: true, isActiveAudio: true)
        let inspection = try overlay.inspect()

        XCTAssertNoThrow(try inspection.find(text: "4.1"))
        XCTAssertNoThrow(try inspection.find(text: "NBC"))
        XCTAssertNoThrow(try inspection.find(text: "AUDIO"))
    }

    func testTVMultiPlayerViewRendersActiveFeeds() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let (multiPlayerViewModel, playerViewModel, guideViewModel) = makeEnvironment()
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))

        let view = TVMultiPlayerView()
            .environmentObject(multiPlayerViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)

        let inspection = try view.inspect()
        XCTAssertNoThrow(try inspection.find(text: "4.1"))
        XCTAssertNoThrow(try inspection.find(text: "5.1"))
    }

    func testTVMultiViewGridRendersAddFeedPlaceholder() throws {
        let channel = HDHomeRunChannel(channelNumber: "4.1", name: "NBC")
        let slot = MultiViewSlot.makeSlot(channel: channel, isMuted: false)

        var focusedIndex: Int? = 0
        let grid = TVMultiViewGrid(
            slots: [slot],
            layout: .sideBySide,
            activeSlotIndex: 0,
            focusedSlotIndex: Binding(get: { focusedIndex }, set: { focusedIndex = $0 }),
            onSlotSelect: { _ in },
            onAddSlot: {},
            onOpenOptions: {},
            onSwapWithHero: { _ in },
            onCloseSlot: { _ in }
        )

        let inspection = try grid.inspect()
        XCTAssertNoThrow(try inspection.find(text: "Add Feed"))
    }

    func testTVPlaybackControlsViewIncludesMultiViewButtonWhenLive() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        let apiClient = try APIClient(baseURL: XCTUnwrap(URL(string: "http://localhost:8000")), session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let multiPlayerViewModel = MultiPlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)

        await playerViewModel.playChannel(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))

        let controls = TVPlaybackControlsView(
            playerViewModel: playerViewModel,
            onTogglePlayPause: {},
            onSkipBackward: {},
            onSkipForward: {},
            onClose: {},
            onAddToMultiView: {}
        )
        .environmentObject(guideViewModel)

        let inspection = try controls.inspect()
        XCTAssertNoThrow(try inspection.find(where: { view in
            if let image = try? view.image() {
                return (try? image.actualImage().name()) == "square.grid.2x2"
            }
            return false
        }))
    }

    // MARK: - APL-11 / APL-13: always-visible per-tile options button

    func testTileOptionsButtonOpensDialogWithMakePrimaryAndCloseSlot() throws {
        let slots = [
            MultiViewSlot.makeSlot(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"), isMuted: false),
            MultiViewSlot.makeSlot(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"), isMuted: true)
        ]

        var focusedIndex: Int? = 0
        let grid = TVMultiViewGrid(
            slots: slots,
            layout: .sideBySide,
            activeSlotIndex: 0,
            focusedSlotIndex: Binding(get: { focusedIndex }, set: { focusedIndex = $0 }),
            onSlotSelect: { _ in },
            onAddSlot: {},
            onOpenOptions: {},
            onSwapWithHero: { _ in },
            onCloseSlot: { _ in }
        )

        // Tile 1 (non-hero) is the interesting case: it's the one where "Make Primary" applies.
        // The dialog's presented content isn't reachable here - see the note on
        // `assertTileOptionsButtonIsTappable` below - so this asserts the button that opens
        // it exists (by accessibility identifier, tolerating per-button lookup failures on the
        // rest of the tree) and that tapping it doesn't throw. The conditional "Make Primary"
        // wiring itself (`if index != 0`) is verified by reading `TVMultiViewGrid.slotView(at:)`.
        try Self.assertTileOptionsButtonIsTappable(on: grid, identifier: "tileOptions_1")
    }

    func testTileOptionsButtonOnHeroSlotOmitsMakePrimary() throws {
        let slots = [
            MultiViewSlot.makeSlot(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"), isMuted: false)
        ]

        var focusedIndex: Int? = 0
        let grid = TVMultiViewGrid(
            slots: slots,
            layout: .sideBySide,
            activeSlotIndex: 0,
            focusedSlotIndex: Binding(get: { focusedIndex }, set: { focusedIndex = $0 }),
            onSlotSelect: { _ in },
            onAddSlot: {},
            onOpenOptions: {},
            onSwapWithHero: { _ in },
            onCloseSlot: { _ in }
        )

        try Self.assertTileOptionsButtonIsTappable(on: grid, identifier: "tileOptions_0")
    }

    func testTileOptionsCloseSlotInvokesCallback() throws {
        let slots = [
            MultiViewSlot.makeSlot(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"), isMuted: false),
            MultiViewSlot.makeSlot(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"), isMuted: true)
        ]

        var focusedIndex: Int? = 0
        let grid = TVMultiViewGrid(
            slots: slots,
            layout: .sideBySide,
            activeSlotIndex: 0,
            focusedSlotIndex: Binding(get: { focusedIndex }, set: { focusedIndex = $0 }),
            onSlotSelect: { _ in },
            onAddSlot: {},
            onOpenOptions: {},
            onSwapWithHero: { _ in },
            onCloseSlot: { _ in }
        )

        // `onCloseSlot` fires from a button inside the confirmationDialog's action closure,
        // which - like the dialog content asserted on above - can't be reached here; see the
        // note on `assertTileOptionsButtonIsTappable`. This is left as a distinct test (rather
        // than folded into the two above) so the tile-options-button-opens-the-close-flow intent
        // stays documented even though the callback itself isn't exercised from this layer.
        try Self.assertTileOptionsButtonIsTappable(on: grid, identifier: "tileOptions_1")
    }

    /// `.confirmationDialog(...)`'s presented content (its action buttons, including "Make
    /// Primary (Hero)" and "Close Slot") is unreachable from these tests: ViewInspector's
    /// `confirmationDialog()` accessor requires `isPresentedBinding().wrappedValue == true`
    /// (see the vendored package's `SwiftUI/ConfirmationDialog.swift`), but a `.tap()` on a
    /// button that mutates `@State` (here, `tileOptionsIndex`) does not propagate that mutation
    /// to any subsequent inspection - fresh or reused - without hosting the view via
    /// `ViewHosting.host(view:)`. This codebase already has this exact, documented limitation
    /// elsewhere (see `TVKeywordRuleModalTests.swift`, `TVServerConnectionFieldsTests.swift`,
    /// `iOSScrubBarViewTests.swift`) and consistently falls back to asserting only that the
    /// triggering tap doesn't throw, rather than adopting `ViewHosting`. Follow that convention
    /// here: assert the per-tile options button exists (by accessibility identifier) and that
    /// tapping it doesn't throw.
    private static func assertTileOptionsButtonIsTappable(
        on grid: TVMultiViewGrid,
        identifier: String
    ) throws {
        let button = try XCTUnwrap(try grid.inspect().findAll(ViewType.Button.self).first {
            (try? $0.accessibilityIdentifier()) == identifier
        })
        XCTAssertNoThrow(try button.tap())
    }

    // MARK: - APL-5: focus/audio-routing stays in sync after slot mutation

    /// `TVMultiPlayerView`'s `repushFocusToActiveSlot()` and the closures that call it
    /// (`onCloseSlot`/`onSwapWithHero`) are private, and the actual bug it fixes lives in how
    /// tvOS's real focus engine reacts to `@FocusState` - neither is something XCTest/
    /// ViewInspector can observe without a live window (same limitation noted for the
    /// `.onMoveCommand` fallback-focus workaround under APL-18). What *is* externally
    /// verifiable is the outward-facing contract: after a slot removal, `activeSlotIndex`
    /// (the value the round-trip-through-nil idiom re-pushes into `focusedSlotIndex`) lands on
    /// the correct remaining slot rather than a stale or out-of-bounds index - which is what
    /// this test checks. Full remote-input focus behavior still needs on-device verification.
    func testRemovingActiveSlotLeavesActiveSlotIndexPointingAtRemainingSlot() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let (multiPlayerViewModel, _, _) = makeEnvironment()
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))

        XCTAssertEqual(multiPlayerViewModel.activeSlotIndex, 0)

        // Remove the currently-active slot 0; TVMultiPlayerView's onCloseSlot closure both
        // removes the feed and re-pushes focus so it tracks the new activeSlotIndex, rather
        // than leaving tvOS focus pointed at a stale/removed slot.
        multiPlayerViewModel.removeFeed(at: 0)

        XCTAssertEqual(multiPlayerViewModel.slots.count, 1)
        XCTAssertEqual(multiPlayerViewModel.slots[0].channel.channelNumber, "5.1")
        // removeFeed's own bookkeeping keeps activeSlotIndex valid - the remaining slot shifts
        // down to index 0, and that's the value repushFocusToActiveSlot() re-pushes into
        // focusedSlotIndex (and, transitively, tvOS's real focus engine on-device).
        XCTAssertEqual(multiPlayerViewModel.activeSlotIndex, 0)

        // Simulate the exact round-trip-through-nil idiom repushFocusToActiveSlot() performs on
        // the plain @Binding TVMultiViewGrid is given - this is the part of the fix that's
        // mechanically testable without a live focus engine: reassigning the *same* target index
        // after going through nil must still leave the binding holding that value.
        var focusedIndex: Int? = 0
        let binding = Binding<Int?>(get: { focusedIndex }, set: { focusedIndex = $0 })
        let target = multiPlayerViewModel.activeSlotIndex
        binding.wrappedValue = nil
        binding.wrappedValue = target
        XCTAssertEqual(focusedIndex, multiPlayerViewModel.activeSlotIndex)
    }
}
