import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSDiscoveryViewTests: XCTestCase {
    private func makeEnvironmentObjects() -> (DiscoveryViewModel, GuideViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let discoveryViewModel = DiscoveryViewModel(apiClient: apiClient)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        return (discoveryViewModel, guideViewModel)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsEmptyStateMessageWhenNoRecommendations() throws {
        let (discoveryViewModel, guideViewModel) = makeEnvironmentObjects()
        XCTAssertTrue(discoveryViewModel.items.isEmpty)

        let view = iOSDiscoveryView()
            .environmentObject(discoveryViewModel)
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "No recommendations right now. Check back after the guide updates."))
    }

    func testHidesNewAndNotableBannerWhenNoItems() throws {
        let (discoveryViewModel, guideViewModel) = makeEnvironmentObjects()

        let view = iOSDiscoveryView()
            .environmentObject(discoveryViewModel)
            .environmentObject(guideViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "New & Notable — record a few shows to get picks tailored to you."))
    }

    func testShowsNewAndNotableBannerWhenColdStart() async throws {
        let (discoveryViewModel, guideViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": false, "items": [{"title": "New & Notable Show", "channel_number": "5.1"}]}
        """.utf8), 200)
        await discoveryViewModel.loadData()
        XCTAssertFalse(discoveryViewModel.hasProfile)

        let view = iOSDiscoveryView()
            .environmentObject(discoveryViewModel)
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "New & Notable — record a few shows to get picks tailored to you."))
        XCTAssertNoThrow(try view.inspect().find(text: "New & Notable Show"))
    }

    func testShowsRecommendedItemsWithMetadata() async throws {
        let (discoveryViewModel, guideViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": true, "items": [
            {
                "title": "Morning Show",
                "episode_title": "The Pilot",
                "channel_number": "4.1",
                "is_new": true,
                "category": "Drama, Suspense"
            }
        ]}
        """.utf8), 200)
        await discoveryViewModel.loadData()
        XCTAssertEqual(discoveryViewModel.items.count, 1)

        let view = iOSDiscoveryView()
            .environmentObject(discoveryViewModel)
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Morning Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "The Pilot"))
        XCTAssertNoThrow(try view.inspect().find(text: "NEW"))
        XCTAssertNoThrow(try view.inspect().find(text: "4.1"))
        XCTAssertNoThrow(try view.inspect().find(text: "Drama"))
        XCTAssertThrowsError(try view.inspect().find(text: "No recommendations right now. Check back after the guide updates."))
    }

    func testHidesNewBadgeAndCategoryWhenAbsent() async throws {
        let (discoveryViewModel, guideViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": true, "items": [{"title": "Evening News", "channel_number": "7.2"}]}
        """.utf8), 200)
        await discoveryViewModel.loadData()

        let view = iOSDiscoveryView()
            .environmentObject(discoveryViewModel)
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Evening News"))
        XCTAssertThrowsError(try view.inspect().find(text: "NEW"))
    }

    func testFilterChipsDisplayAllBucketLabels() throws {
        let (discoveryViewModel, guideViewModel) = makeEnvironmentObjects()

        let view = iOSDiscoveryView()
            .environmentObject(discoveryViewModel)
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "All"))
        XCTAssertNoThrow(try view.inspect().find(text: "Shows"))
        XCTAssertNoThrow(try view.inspect().find(text: "Movies"))
        XCTAssertNoThrow(try view.inspect().find(text: "Sports"))
    }

    func testSettingFilterNarrowsDisplayedItemsToThatBucket() async throws {
        let (discoveryViewModel, guideViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": true, "items": [
            {"title": "Personalized Drama", "bucket": "shows", "source": "personalized"},
            {"title": "Lakers at Celtics", "bucket": "sports", "source": "favorite_team"}
        ]}
        """.utf8), 200)
        await discoveryViewModel.loadData()
        discoveryViewModel.filter = .sports

        let view = iOSDiscoveryView()
            .environmentObject(discoveryViewModel)
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Lakers at Celtics"))
        XCTAssertThrowsError(try view.inspect().find(text: "Personalized Drama"))
    }

    func testShowsSourceBadgeOnlyForNonPersonalizedItems() async throws {
        let (discoveryViewModel, guideViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": true, "items": [
            {"title": "Personalized Drama", "bucket": "shows", "source": "personalized"},
            {"title": "Oscar Marathon", "bucket": "movies", "source": "network_pick"}
        ]}
        """.utf8), 200)
        await discoveryViewModel.loadData()

        let view = iOSDiscoveryView()
            .environmentObject(discoveryViewModel)
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Network pick"))
    }

    func testChannelLookupFallsBackToBareChannelWhenGuideHasNoMatch() async throws {
        let (discoveryViewModel, guideViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels": [{"channel_number": "4.1", "name": "KTEST", "is_hd": true, "is_drm": false, "stream_url": "http://localhost/4.1"}], "guide_available": true}
        """.utf8), 200)
        await guideViewModel.loadChannels()
        XCTAssertEqual(guideViewModel.channels.map(\.channelNumber), ["4.1"])

        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": true, "items": [{"title": "Unmapped Show", "channel_number": "99.9"}]}
        """.utf8), 200)
        await discoveryViewModel.loadData()

        let view = iOSDiscoveryView()
            .environmentObject(discoveryViewModel)
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Unmapped Show"))
    }
}
