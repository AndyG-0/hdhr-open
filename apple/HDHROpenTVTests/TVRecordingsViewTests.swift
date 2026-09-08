import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVRecordingsViewTests: XCTestCase {
    private func makeEnvironmentObjects() -> (RecordingsViewModel, PlayerViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        return (
            RecordingsViewModel(apiClient: apiClient),
            PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        )
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsEmptyStateWhenNoRecordingsAfterLoad() async throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/dvr/info"] = (Data("{}".utf8), 200)
        await recordingsViewModel.loadData()

        let view = TVRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "No recordings in this category"))
    }

    func testShowsRecordingCardsWhenLoaded() async throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data("""
        [{"recording_id":"rec1","title":"Morning Show"}]
        """.utf8), 200)
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/dvr/info"] = (Data("{}".utf8), 200)
        await recordingsViewModel.loadData()
        XCTAssertEqual(recordingsViewModel.recordings.count, 1)

        let view = TVRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(TVRecordingCardView.self))
        XCTAssertThrowsError(try view.inspect().find(text: "No recordings in this category"))
    }

    func testShowsRulesCountBadge() async throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID":"r1","SeriesID":"SH1","Title":"Morning Show"}]
        """.utf8), 200)
        MockURLProtocol.handlers["/api/dvr/info"] = (Data("{}".utf8), 200)
        await recordingsViewModel.loadData()
        XCTAssertEqual(recordingsViewModel.recordingRules.count, 1)

        let view = TVRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Rules (1)"))
    }

    func testShowsFreeSpaceWhenDvrInfoLoaded() async throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/dvr/info"] = (Data("""
        {"friendly_name":"HDHomeRun DVR","free_space_bytes":2147483648}
        """.utf8), 200)
        await recordingsViewModel.loadData()

        let view = TVRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "2.0 GB free"))
    }

    func testShowsCategoryFilterPills() throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        let view = TVRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        for category in RecordingCategoryFilter.allCases {
            XCTAssertNoThrow(try view.inspect().find(text: category.rawValue), "Missing filter pill: \(category.rawValue)")
        }
    }
}
