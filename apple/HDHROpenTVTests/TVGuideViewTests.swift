import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVGuideViewTests: XCTestCase {
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

    private func makeView(_ guideViewModel: GuideViewModel, _ playerViewModel: PlayerViewModel) -> some View {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let multiPlayerViewModel = MultiPlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        return TVGuideView()
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(multiPlayerViewModel)
    }

    func testShowsEmptyStateWhenNoChannels() throws {
        let (guideViewModel, playerViewModel) = makeEnvironmentObjects()
        XCTAssertTrue(guideViewModel.channels.isEmpty)

        let view = makeView(guideViewModel, playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "No channels discovered"))
    }

    func testShowsFavoritesEmptyMessageWhenFilteringWithNoFavorites() throws {
        let (guideViewModel, playerViewModel) = makeEnvironmentObjects()
        guideViewModel.filterOnlyFavorites = true

        let view = makeView(guideViewModel, playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "No favorite channels"))
    }

    func testShowsChannelRowsWhenChannelsLoaded() async throws {
        let (guideViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels":[
          {"channel_number":"5.1","name":"WXYZ","is_hd":true,"is_drm":false,"stream_url":"http://x/5.1"},
          {"channel_number":"7.1","name":"KABC","is_hd":false,"is_drm":false,"stream_url":"http://x/7.1"}
        ],"guide_available":true}
        """.utf8), 200)

        await guideViewModel.loadChannels()
        XCTAssertEqual(guideViewModel.channels.count, 2)

        let view = makeView(guideViewModel, playerViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "No channels discovered"))
        XCTAssertEqual(try view.inspect().findAll(TVChannelRowView.self).count, 2)
        XCTAssertNoThrow(try view.inspect().find(text: "WXYZ"))
        XCTAssertNoThrow(try view.inspect().find(text: "KABC"))
    }

    func testShowsLiveTVGuideHeader() throws {
        let (guideViewModel, playerViewModel) = makeEnvironmentObjects()
        let view = makeView(guideViewModel, playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Live TV Guide"))
    }

    func testTappingFavoritesOnlyButtonTogglesFilter() throws {
        let (guideViewModel, playerViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(guideViewModel.filterOnlyFavorites)

        let view = makeView(guideViewModel, playerViewModel)

        try view.inspect().find(button: "Favorites Only").tap()

        XCTAssertTrue(guideViewModel.filterOnlyFavorites)
    }
}
