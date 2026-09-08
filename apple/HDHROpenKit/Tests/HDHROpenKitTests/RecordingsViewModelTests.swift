import XCTest
@testable import HDHROpenKit

@MainActor
final class RecordingsViewModelTests: XCTestCase {
    private func makeMockedAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    /// Populates `vm.recordings` via the real load path (recordings is a
    /// private(set) property, so tests go through the mocked API rather than
    /// poking internal state directly).
    private func loadRecordings(_ vm: RecordingsViewModel, json: String) async {
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data(json.utf8), 200)
        await vm.loadRecordings()
    }

    // MARK: - Filter branches

    func testFilteredRecordingsAllReturnsEverything() async {
        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await loadRecordings(vm, json: """
        [{"recording_id": "1", "title": "A"}, {"recording_id": "2", "title": "B", "category_type": "movies"}]
        """)
        vm.selectedFilter = .all
        XCTAssertEqual(vm.filteredRecordings.count, 2)
    }

    func testFilteredRecordingsShowsByCategoryType() async {
        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await loadRecordings(vm, json: """
        [
            {"recording_id": "1", "title": "A", "category_type": "shows"},
            {"recording_id": "2", "title": "B", "season_number": 3},
            {"recording_id": "3", "title": "C", "category_type": "movies"}
        ]
        """)
        vm.selectedFilter = .shows
        XCTAssertEqual(Set(vm.filteredRecordings.map(\.recordingId)), ["1", "2"])
    }

    func testFilteredRecordingsMoviesByTypeOrCategoryText() async {
        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await loadRecordings(vm, json: """
        [
            {"recording_id": "1", "title": "A", "category_type": "movies"},
            {"recording_id": "2", "title": "B", "category": "Action Movie"},
            {"recording_id": "3", "title": "C", "category_type": "shows"}
        ]
        """)
        vm.selectedFilter = .movies
        XCTAssertEqual(Set(vm.filteredRecordings.map(\.recordingId)), ["1", "2"])
    }

    func testFilteredRecordingsSportsByTypeOrCategoryText() async {
        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await loadRecordings(vm, json: """
        [
            {"recording_id": "1", "title": "A", "category_type": "sports"},
            {"recording_id": "2", "title": "B", "category": "Live Sporting Event"},
            {"recording_id": "3", "title": "C", "category_type": "shows"}
        ]
        """)
        vm.selectedFilter = .sports
        XCTAssertEqual(Set(vm.filteredRecordings.map(\.recordingId)), ["1", "2"])
    }

    func testFilteredRecordingsInProgress() async {
        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        let future = Date().timeIntervalSince1970 + 3600
        let past = Date().timeIntervalSince1970 - 3600
        await loadRecordings(vm, json: """
        [{"recording_id": "1", "title": "A", "record_end": \(future)}, {"recording_id": "2", "title": "B", "record_end": \(past)}]
        """)
        vm.selectedFilter = .inProgress
        XCTAssertEqual(vm.filteredRecordings.map(\.recordingId), ["1"])
    }

    func testInProgressAndCompletedRecordings() async {
        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        let future = Date().timeIntervalSince1970 + 3600
        let past = Date().timeIntervalSince1970 - 3600
        await loadRecordings(vm, json: """
        [{"recording_id": "1", "title": "A", "record_end": \(future)}, {"recording_id": "2", "title": "B", "record_end": \(past)}]
        """)
        XCTAssertEqual(vm.inProgressRecordings.map(\.recordingId), ["1"])
        XCTAssertEqual(vm.completedRecordings.map(\.recordingId), ["2"])
    }

    // MARK: - Loading states

    func testLoadDataPopulatesRecordingsRulesAndDvrInfo() async {
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data("""
        [{"recording_id": "rec1", "title": "Show 1"}]
        """.utf8), 200)
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID": "rule1", "SeriesID": "series1", "Title": "Rule Show"}]
        """.utf8), 200)
        MockURLProtocol.handlers["/api/dvr/info"] = (Data("""
        {"friendly_name": "HDHomeRun DVR", "is_builtin": true}
        """.utf8), 200)

        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await vm.loadData()

        XCTAssertFalse(vm.isLoading)
        XCTAssertEqual(vm.recordings.count, 1)
        XCTAssertEqual(vm.recordingRules.count, 1)
        XCTAssertNotNil(vm.dvrInfo)
        XCTAssertNil(vm.error)
    }

    func testLoadRecordingsFailureSetsError() async {
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await vm.loadRecordings()

        XCTAssertNotNil(vm.error)
        XCTAssertTrue(vm.recordings.isEmpty)
    }

    func testLoadRulesFailureIsSilent() async {
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await vm.loadRules()

        XCTAssertTrue(vm.recordingRules.isEmpty)
        XCTAssertNil(vm.error)
    }

    func testLoadDvrInfoFailureIsSilent() async {
        MockURLProtocol.handlers["/api/dvr/info"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await vm.loadDvrInfo()

        XCTAssertNil(vm.dvrInfo)
        XCTAssertNil(vm.error)
    }

    // MARK: - Recording rule CRUD

    func testDeleteRecordingRemovesFromList() async throws {
        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await loadRecordings(vm, json: """
        [{"recording_id": "rec1", "title": "A"}, {"recording_id": "rec2", "title": "B"}]
        """)
        MockURLProtocol.handlers["/api/dvr/recordings/rec1"] = (Data("{}".utf8), 200)

        try await vm.deleteRecording(XCTUnwrap(vm.recordings.first { $0.recordingId == "rec1" }))

        XCTAssertEqual(vm.recordings.map(\.recordingId), ["rec2"])
    }

    func testDeleteRecordingWithNilIdIsNoOp() async throws {
        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        await loadRecordings(vm, json: """
        [{"recording_id": "rec1", "title": "A"}]
        """)
        let recordingWithoutId = HDHomeRunRecording(title: "No ID")

        try await vm.deleteRecording(recordingWithoutId)

        XCTAssertEqual(vm.recordings.map(\.recordingId), ["rec1"])
    }

    func testDeleteRuleUpdatesRecordingRules() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-rules/rule1"] = (Data("""
        [{"RecordingRuleID": "rule2", "SeriesID": "series2", "Title": "Remaining Rule"}]
        """.utf8), 200)

        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        try await vm.deleteRule(ruleId: "rule1")

        XCTAssertEqual(vm.recordingRules.map(\.recordingRuleId), ["rule2"])
    }

    func testAddRecordingRuleUpdatesRecordingRules() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID": "rule1", "SeriesID": "series1", "Title": "New Rule"}]
        """.utf8), 200)

        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        let payload = AddRecordingRulePayload(seriesId: "series1", title: "New Rule")
        try await vm.addRecordingRule(payload: payload)

        XCTAssertEqual(vm.recordingRules.map(\.recordingRuleId), ["rule1"])
    }

    func testUpdateRecordingRuleUpdatesRecordingRules() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-rules/rule1"] = (Data("""
        [{"RecordingRuleID": "rule1", "SeriesID": "series1", "Title": "Updated Rule"}]
        """.utf8), 200)

        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        let payload = AddRecordingRulePayload(seriesId: "series1", title: "Updated Rule")
        try await vm.updateRecordingRule(ruleId: "rule1", payload: payload)

        XCTAssertEqual(vm.recordingRules.first?.title, "Updated Rule")
    }

    func testCreateKeywordRuleAddsRule() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID": "kw1", "SeriesID": "auto", "Title": "Breaking News", "KeywordQuery": "breaking"}]
        """.utf8), 200)

        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        var options = RecordingRuleOptions()
        options.keywordQuery = "breaking"
        options.titleMatchMode = "contains"
        try await vm.createKeywordRule(title: "Breaking News", options: options)

        XCTAssertEqual(vm.recordingRules.first?.keywordQuery, "breaking")
    }

    func testAddRecordingRuleFailurePropagatesAndLeavesRulesUnchanged() async {
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("{\"detail\":\"nope\"}".utf8), 500)

        let vm = RecordingsViewModel(apiClient: makeMockedAPIClient())
        let payload = AddRecordingRulePayload(seriesId: "series1", title: "New Rule")

        do {
            try await vm.addRecordingRule(payload: payload)
            XCTFail("expected error to be thrown")
        } catch {
            XCTAssertTrue(vm.recordingRules.isEmpty)
        }
    }
}
