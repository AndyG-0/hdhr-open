import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSRecordingsViewTests: XCTestCase {
    private func makeEnvironmentObjects() -> (RecordingsViewModel, PlayerViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let recordingsViewModel = RecordingsViewModel(apiClient: apiClient)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        return (recordingsViewModel, playerViewModel)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsNoRecordingsMessageAndZeroCountWhenEmpty() throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        XCTAssertTrue(recordingsViewModel.recordings.isEmpty)

        let view = iOSRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "No recordings available"))
        XCTAssertNoThrow(try view.inspect().find(text: "0 Recordings"))
    }

    func testHidesFreeSpaceHeaderWhenDvrInfoNotLoaded() throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        XCTAssertNil(recordingsViewModel.dvrInfo)

        let view = iOSRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "HDHomeRun RECORD"))
    }

    func testShowsFreeSpaceHeaderWhenDvrInfoLoaded() async throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/dvr/info"] = (Data("""
        {"friendly_name":"HDHomeRun RECORD","free_space_bytes":2147483648,"is_builtin":false}
        """.utf8), 200)
        await recordingsViewModel.loadDvrInfo()
        XCTAssertNotNil(recordingsViewModel.dvrInfo)

        let view = iOSRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "HDHomeRun RECORD"))
        XCTAssertNoThrow(try view.inspect().find(text: "2.0 GB free"))
    }

    func testShowsRecordingsListWithMetadataAndRecBadgeForInProgress() async throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        let now = Date().timeIntervalSince1970
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data("""
        [
            {"title":"Live Game","record_end":\(now + 1800)},
            {"title":"Today Show","episode_title":"Pilot","season_number":1,"episode_number":"2","duration_seconds":3665,"record_end":\(now - 1800)}
        ]
        """.utf8), 200)
        await recordingsViewModel.loadRecordings()
        XCTAssertEqual(recordingsViewModel.recordings.count, 2)

        let view = iOSRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "2 Recordings"))
        XCTAssertNoThrow(try view.inspect().find(text: "Live Game"))
        XCTAssertNoThrow(try view.inspect().find(text: "Today Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "Pilot"))
        XCTAssertNoThrow(try view.inspect().find(text: "1h 1m"))
        XCTAssertNoThrow(try view.inspect().find(text: "REC"))
    }

    func testFiltersRecordingsByCategorySelection() async throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data("""
        [
            {"title":"Action Movie","category_type":"movies"},
            {"title":"Weekly Show","season_number":2,"category_type":"shows"}
        ]
        """.utf8), 200)
        await recordingsViewModel.loadRecordings()
        XCTAssertEqual(recordingsViewModel.recordings.count, 2)

        recordingsViewModel.selectedFilter = .movies
        XCTAssertEqual(recordingsViewModel.filteredRecordings.map(\.title), ["Action Movie"])

        let view = iOSRecordingsView()
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "1 Recordings"))
        XCTAssertNoThrow(try view.inspect().find(text: "Action Movie"))
        XCTAssertThrowsError(try view.inspect().find(text: "Weekly Show"))
    }
}
