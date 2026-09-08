import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSMultiPlayerViewTests: XCTestCase {
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

    func testIOSMultiPlayerViewRendersActiveFeeds() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let (multiPlayerViewModel, playerViewModel, guideViewModel) = makeEnvironment()
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))

        let view = iOSMultiPlayerView()
            .environmentObject(multiPlayerViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)

        let inspection = try view.inspect()
        XCTAssertNoThrow(try inspection.find(text: "4.1"))
        XCTAssertNoThrow(try inspection.find(text: "NBC"))
        XCTAssertNoThrow(try inspection.find(text: "5.1"))
        XCTAssertNoThrow(try inspection.find(text: "CBS"))
        XCTAssertNoThrow(try inspection.find(text: "AUDIO"))
    }

    func testIOSMultiPlayerViewRendersAddChannelPlaceholder() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")

        let (multiPlayerViewModel, playerViewModel, guideViewModel) = makeEnvironment()
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))

        let view = iOSMultiPlayerView()
            .environmentObject(multiPlayerViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)

        let inspection = try view.inspect()
        XCTAssertNoThrow(try inspection.find(text: "Add Channel"))
    }

    func testIOSMultiPlayerViewTapToRouteAudio() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")

        let (multiPlayerViewModel, _, _) = makeEnvironment()
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))

        XCTAssertEqual(multiPlayerViewModel.activeSlotIndex, 0)
        XCTAssertFalse(multiPlayerViewModel.slots[0].isMuted)
        XCTAssertTrue(multiPlayerViewModel.slots[1].isMuted)

        // Switch audio focus to slot 1
        multiPlayerViewModel.setAudioSlot(index: 1)

        XCTAssertEqual(multiPlayerViewModel.activeSlotIndex, 1)
        XCTAssertTrue(multiPlayerViewModel.slots[0].isMuted)
        XCTAssertFalse(multiPlayerViewModel.slots[1].isMuted)
    }

    func testIOSMultiPlayerViewLayoutTransitions() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")
        setupMockFeed(channelNumber: "5.1", sessId: "sess2")
        setupMockFeed(channelNumber: "7.1", sessId: "sess3")

        let (multiPlayerViewModel, _, _) = makeEnvironment()
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        XCTAssertEqual(multiPlayerViewModel.layout, .sideBySide)

        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "5.1", name: "CBS"))
        XCTAssertEqual(multiPlayerViewModel.layout, .sideBySide)

        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "7.1", name: "ABC"))
        XCTAssertEqual(multiPlayerViewModel.layout, .threeBox)

        multiPlayerViewModel.layout = .quad
        XCTAssertEqual(multiPlayerViewModel.layout, .quad)
    }

    func testIOSMultiPlayerViewDoneButtonClosesAll() async throws {
        setupMockFeed(channelNumber: "4.1", sessId: "sess1")

        let (multiPlayerViewModel, playerViewModel, guideViewModel) = makeEnvironment()
        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        XCTAssertTrue(multiPlayerViewModel.isMultiViewActive)

        let view = iOSMultiPlayerView()
            .environmentObject(multiPlayerViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)

        let inspection = try view.inspect()
        let doneButton = try inspection.find(button: "Done")
        try doneButton.tap()

        XCTAssertFalse(multiPlayerViewModel.isMultiViewActive)
        XCTAssertTrue(multiPlayerViewModel.slots.isEmpty)
    }
}
