import XCTest
@testable import HDHROpenKit

@MainActor
final class DiscoveryViewModelTests: XCTestCase {
    private func makeMockedAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testInitialStateIsEmptyAndDisabled() {
        let vm = DiscoveryViewModel(apiClient: makeMockedAPIClient())

        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertFalse(vm.hasProfile)
        XCTAssertFalse(vm.enabled)
        XCTAssertFalse(vm.isLoading)
        XCTAssertNil(vm.error)
        XCTAssertEqual(vm.filter, .all)
        XCTAssertTrue(vm.filteredItems.isEmpty)
    }

    func testFilteredItemsDefaultsToAllItemsUnfiltered() async {
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": true, "items": [
            {"title": "Personalized Drama", "bucket": "shows", "source": "personalized"},
            {"title": "Oscar Marathon", "bucket": "movies", "source": "network_pick"},
            {"title": "Lakers at Celtics", "bucket": "sports", "source": "favorite_team"}
        ]}
        """.utf8), 200)

        let vm = DiscoveryViewModel(apiClient: makeMockedAPIClient())
        await vm.loadData()

        XCTAssertEqual(vm.items.count, 3)
        XCTAssertEqual(vm.filteredItems.count, 3)
    }

    func testSettingFilterNarrowsFilteredItemsToThatBucket() async {
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": true, "items": [
            {"title": "Personalized Drama", "bucket": "shows", "source": "personalized"},
            {"title": "Oscar Marathon", "bucket": "movies", "source": "network_pick"},
            {"title": "Lakers at Celtics", "bucket": "sports", "source": "favorite_team"}
        ]}
        """.utf8), 200)

        let vm = DiscoveryViewModel(apiClient: makeMockedAPIClient())
        await vm.loadData()
        vm.filter = .sports

        XCTAssertEqual(vm.filteredItems.map(\.title), ["Lakers at Celtics"])
    }

    func testSwitchingBackToAllRestoresEveryItem() async {
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": true, "items": [
            {"title": "Personalized Drama", "bucket": "shows", "source": "personalized"},
            {"title": "Oscar Marathon", "bucket": "movies", "source": "network_pick"},
            {"title": "Lakers at Celtics", "bucket": "sports", "source": "favorite_team"}
        ]}
        """.utf8), 200)

        let vm = DiscoveryViewModel(apiClient: makeMockedAPIClient())
        await vm.loadData()
        vm.filter = .shows
        vm.filter = .all

        XCTAssertEqual(vm.filteredItems.count, 3)
    }

    func testLoadDataPopulatesStateFromResponse() async {
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": true, "items": [{"title": "Show A", "channel_number": "4.1"}]}
        """.utf8), 200)

        let vm = DiscoveryViewModel(apiClient: makeMockedAPIClient())
        await vm.loadData()

        XCTAssertTrue(vm.enabled)
        XCTAssertTrue(vm.hasProfile)
        XCTAssertEqual(vm.items.map(\.title), ["Show A"])
        XCTAssertFalse(vm.isLoading)
        XCTAssertNil(vm.error)
    }

    func testLoadDataWithColdStartFallback() async {
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": true, "has_profile": false, "items": [{"title": "New & Notable Show", "channel_number": "5.1"}]}
        """.utf8), 200)

        let vm = DiscoveryViewModel(apiClient: makeMockedAPIClient())
        await vm.loadData()

        XCTAssertTrue(vm.enabled)
        XCTAssertFalse(vm.hasProfile)
        XCTAssertEqual(vm.items.count, 1)
    }

    func testLoadDataWhenFeatureDisabled() async {
        MockURLProtocol.handlers["/api/discovery"] = (Data("""
        {"enabled": false, "has_profile": false, "items": []}
        """.utf8), 200)

        let vm = DiscoveryViewModel(apiClient: makeMockedAPIClient())
        await vm.loadData()

        XCTAssertFalse(vm.enabled)
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertNil(vm.error)
    }

    func testLoadDataFailureSetsErrorAndLeavesItemsEmpty() async {
        MockURLProtocol.handlers["/api/discovery"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = DiscoveryViewModel(apiClient: makeMockedAPIClient())
        await vm.loadData()

        XCTAssertNotNil(vm.error)
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertFalse(vm.isLoading)
    }
}
