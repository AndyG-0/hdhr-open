import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSGuideViewTests: XCTestCase {
    private func makeEnvironmentObjects() -> (GuideViewModel, PlayerViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        return (guideViewModel, playerViewModel)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testPassesLoadedChannelsToGuideGridView() async throws {
        let (guideViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels":[
            {"channel_number":"4.1","name":"WNBC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null},
            {"channel_number":"5.1","name":"WABC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null}
        ],"guide_available":true}
        """.utf8), 200)
        await guideViewModel.loadChannels()
        XCTAssertEqual(guideViewModel.channels.count, 2)

        let view = iOSGuideView()
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)

        let grid = try view.inspect().find(iOSGuideGridView.self)
        XCTAssertEqual(try grid.actualView().channels.count, 2)
    }

    func testFiltersToFavoritesOnlyWhenToggleEnabled() async throws {
        let (guideViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels":[
            {"channel_number":"4.1","name":"WNBC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null},
            {"channel_number":"5.1","name":"WABC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null}
        ],"guide_available":true}
        """.utf8), 200)
        await guideViewModel.loadChannels()
        await guideViewModel.toggleFavorite(channelNumber: "4.1")
        guideViewModel.filterOnlyFavorites = true
        XCTAssertEqual(guideViewModel.displayedChannels.count, 1)

        let view = iOSGuideView()
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)

        let grid = try view.inspect().find(iOSGuideGridView.self)
        XCTAssertEqual(try grid.actualView().channels.map(\.channelNumber), ["4.1"])
    }

    func testShowsAllChannelsWhenFavoritesFilterDisabled() async throws {
        let (guideViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels":[
            {"channel_number":"4.1","name":"WNBC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null},
            {"channel_number":"5.1","name":"WABC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null}
        ],"guide_available":true}
        """.utf8), 200)
        await guideViewModel.loadChannels()
        await guideViewModel.toggleFavorite(channelNumber: "4.1")
        XCTAssertFalse(guideViewModel.filterOnlyFavorites)

        let view = iOSGuideView()
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)

        let grid = try view.inspect().find(iOSGuideGridView.self)
        XCTAssertEqual(try grid.actualView().channels.count, 2)
    }
}
