import XCTest
@testable import HDHROpenKit

@MainActor
final class GuideViewModelTests: XCTestCase {
    private func makeMockedAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    private func makeViewModel(apiClient: APIClient? = nil) -> GuideViewModel {
        let client = apiClient ?? makeMockedAPIClient()
        return GuideViewModel(apiClient: client, watchSessionManager: WatchSessionManager(apiClient: client))
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    // MARK: - displayedChannels

    func testDisplayedChannelsReturnsAllWhenNotFilteringFavorites() async {
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels": [{"channel_number": "4.1", "name": "A", "is_hd": true, "is_drm": false, "stream_url": "http://x"}, {"channel_number": "5.1", "name": "B", "is_hd": true, "is_drm": false, "stream_url": "http://x"}], "guide_available": true}
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadChannels()

        XCTAssertEqual(vm.displayedChannels.count, 2)
    }

    func testDisplayedChannelsReturnsAllWhenFavoritesEmptyEvenIfFiltering() async {
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels": [{"channel_number": "4.1", "name": "A", "is_hd": true, "is_drm": false, "stream_url": "http://x"}], "guide_available": true}
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadChannels()
        vm.filterOnlyFavorites = true

        XCTAssertEqual(vm.displayedChannels.count, 1)
    }

    func testDisplayedChannelsFiltersToFavoritesWhenSet() async {
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels": [{"channel_number": "4.1", "name": "A", "is_hd": true, "is_drm": false, "stream_url": "http://x"}, {"channel_number": "5.1", "name": "B", "is_hd": true, "is_drm": false, "stream_url": "http://x"}], "guide_available": true}
        """.utf8), 200)
        MockURLProtocol.handlers["/api/network-settings/hdhomerun"] = (Data("""
        {"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {"favorite_channels": ["4.1"]}}
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadChannels()
        await vm.loadFavorites()
        vm.filterOnlyFavorites = true

        XCTAssertEqual(vm.displayedChannels.map(\.channelNumber), ["4.1"])
    }

    // MARK: - loadChannels / loadGuide / loadFavorites / loadRules

    func testLoadChannelsSuccess() async {
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels": [{"channel_number": "4.1", "name": "A", "is_hd": true, "is_drm": false, "stream_url": "http://x"}], "guide_available": true}
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadChannels()

        XCTAssertEqual(vm.channels.count, 1)
        XCTAssertTrue(vm.guideAvailable)
        XCTAssertNil(vm.error)
    }

    func testLoadChannelsFailureSetsError() async {
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = makeViewModel()
        await vm.loadChannels()

        XCTAssertNotNil(vm.error)
        XCTAssertTrue(vm.channels.isEmpty)
    }

    func testLoadGuideSuccess() async {
        MockURLProtocol.handlers["/api/guide"] = (Data("""
        [{"channel_number": "4.1", "channel_name": "A", "airings": [{"title": "Show", "start": 1700000000, "end": 1700003600}]}]
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadGuide()

        XCTAssertEqual(vm.fullGuide.count, 1)
        XCTAssertEqual(vm.fullGuide.first?.airings.first?.title, "Show")
    }

    func testLoadGuideFailureIsSilent() async {
        MockURLProtocol.handlers["/api/guide"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = makeViewModel()
        await vm.loadGuide()

        XCTAssertTrue(vm.fullGuide.isEmpty)
    }

    func testLoadFavoritesParsesFavoriteChannels() async {
        MockURLProtocol.handlers["/api/network-settings/hdhomerun"] = (Data("""
        {"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {"favorite_channels": ["4.1", "5.1"]}}
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadFavorites()

        XCTAssertEqual(vm.favoriteChannels, ["4.1", "5.1"])
    }

    func testLoadFavoritesFailureIsSilentAndOptional() async {
        MockURLProtocol.handlers["/api/network-settings/hdhomerun"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = makeViewModel()
        await vm.loadFavorites()

        XCTAssertTrue(vm.favoriteChannels.isEmpty)
    }

    func testLoadRulesSuccess() async {
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID": "rule1", "SeriesID": "series1", "Title": "Rule"}]
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadRules()

        XCTAssertEqual(vm.recordingRules.map(\.recordingRuleId), ["rule1"])
    }

    func testLoadRulesFailureIsSilent() async {
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = makeViewModel()
        await vm.loadRules()

        XCTAssertTrue(vm.recordingRules.isEmpty)
    }

    func testLoadDataPopulatesEverythingAndTogglesIsLoading() async {
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels": [{"channel_number": "4.1", "name": "A", "is_hd": true, "is_drm": false, "stream_url": "http://x"}], "guide_available": true}
        """.utf8), 200)
        MockURLProtocol.handlers["/api/guide"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/network-settings/hdhomerun"] = (Data("""
        {"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {}}
        """.utf8), 200)
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("[]".utf8), 200)

        let vm = makeViewModel()
        await vm.loadData()

        XCTAssertFalse(vm.isLoading)
        XCTAssertEqual(vm.channels.count, 1)
        XCTAssertNil(vm.error)
    }

    // MARK: - Favorites toggling

    func testToggleFavoriteAddsChannel() async {
        MockURLProtocol.handlers["/api/network-settings/hdhomerun"] = (Data("""
        {"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {}}
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.toggleFavorite(channelNumber: "4.1")

        XCTAssertTrue(vm.favoriteChannels.contains("4.1"))
    }

    func testToggleFavoriteRemovesChannelWhenAlreadyFavorited() async {
        MockURLProtocol.handlers["/api/network-settings/hdhomerun"] = (Data("""
        {"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {"favorite_channels": ["4.1"]}}
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadFavorites()
        XCTAssertTrue(vm.favoriteChannels.contains("4.1"))

        await vm.toggleFavorite(channelNumber: "4.1")

        XCTAssertFalse(vm.favoriteChannels.contains("4.1"))
    }

    func testToggleFavoriteKeepsOptimisticStateWhenPersistFails() async {
        // The update endpoint fails, but toggleFavorite() applies the local
        // set change before attempting to persist and never rolls it back -
        // this exercises that "fire and forget, log on failure" branch.
        MockURLProtocol.handlers["/api/network-settings/hdhomerun"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = makeViewModel()
        await vm.toggleFavorite(channelNumber: "4.1")

        XCTAssertTrue(vm.favoriteChannels.contains("4.1"))
    }

    // MARK: - findRule

    func testFindRuleDelegatesToRecordingRuleMatcher() async {
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID": "rule1", "SeriesID": "series1", "Title": "Nature Documentary"}]
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadRules()

        let airing = HDHomeRunGuideEntry(seriesId: "series1", title: "Nature Documentary", start: 1_700_000_000, end: 1_700_003_600, channelNumber: "5.1")
        let match = vm.findRule(for: "5.1", airing: airing)

        XCTAssertEqual(match?.recordingRuleId, "rule1")
    }

    func testFindRuleReturnsNilWithoutAiring() {
        let vm = makeViewModel()
        XCTAssertNil(vm.findRule(for: "5.1", airing: nil))
    }

    // MARK: - Recording rule interactions

    func testRecordEpisodeAddsRuleAndReloadsRules() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID": "rule1", "SeriesID": "auto", "Title": "Live Event", "DateTimeOnly": 1700000000}]
        """.utf8), 200)

        let vm = makeViewModel()
        try await vm.recordEpisode(channelNumber: "4.1", start: 1_700_000_000)

        XCTAssertEqual(vm.recordingRules.map(\.recordingRuleId), ["rule1"])
    }

    func testRecordSeriesAddsRuleAndReloadsRules() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID": "rule2", "SeriesID": "series1", "Title": "Nature Documentary"}]
        """.utf8), 200)

        let vm = makeViewModel()
        try await vm.recordSeries(seriesId: "series1", channelNumber: "4.1")

        XCTAssertEqual(vm.recordingRules.map(\.recordingRuleId), ["rule2"])
    }

    func testUpdateRuleUpdatesRuleAndReloads() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-rules/rule1"] = (Data("""
        [{"RecordingRuleID": "rule1", "SeriesID": "series1", "Title": "Updated"}]
        """.utf8), 200)
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID": "rule1", "SeriesID": "series1", "Title": "Updated"}]
        """.utf8), 200)

        let vm = makeViewModel()
        try await vm.updateRule(ruleId: "rule1", isSeries: true, seriesId: "series1")

        XCTAssertEqual(vm.recordingRules.first?.title, "Updated")
    }

    func testCancelRuleDeletesRuleAndReloads() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-rules/rule1"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("[]".utf8), 200)

        let vm = makeViewModel()
        try await vm.cancelRule(ruleId: "rule1")

        XCTAssertTrue(vm.recordingRules.isEmpty)
    }

    // MARK: - getAirings

    func testGetAiringsPrefersFullGuideWhenAvailable() async {
        MockURLProtocol.handlers["/api/guide"] = (Data("""
        [{"channel_number": "4.1", "channel_name": "A", "airings": [{"title": "From Full Guide", "start": 1700000000, "end": 1700003600}]}]
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadGuide()

        let airings = vm.getAirings(for: "4.1")

        XCTAssertEqual(airings.map(\.title), ["From Full Guide"])
    }

    func testGetAiringsFallsBackToChannelNowNext() async {
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels": [{"channel_number": "4.1", "name": "A", "now": {"title": "Now Show"}, "next": {"title": "Next Show"}, "is_hd": true, "is_drm": false, "stream_url": "http://x"}], "guide_available": true}
        """.utf8), 200)

        let vm = makeViewModel()
        await vm.loadChannels()

        let airings = vm.getAirings(for: "4.1")

        XCTAssertEqual(airings.map(\.title), ["Now Show", "Next Show"])
    }

    func testGetAiringsReturnsEmptyWhenChannelUnknown() {
        let vm = makeViewModel()
        XCTAssertTrue(vm.getAirings(for: "99.1").isEmpty)
    }
}
