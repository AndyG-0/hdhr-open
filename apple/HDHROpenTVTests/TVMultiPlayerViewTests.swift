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
            onExpandToFullScreen: { _ in },
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
}
