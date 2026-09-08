import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSRecordingRulesSheetTests: XCTestCase {
    private func makeRecordingsViewModel() -> RecordingsViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        return RecordingsViewModel(apiClient: apiClient)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsNoRulesMessageWhenEmpty() throws {
        let recordingsViewModel = makeRecordingsViewModel()
        XCTAssertTrue(recordingsViewModel.recordingRules.isEmpty)

        let view = iOSRecordingRulesSheet().environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "No scheduled rules."))
    }

    func testShowsAddKeywordRuleToolbarButton() throws {
        let recordingsViewModel = makeRecordingsViewModel()
        let view = iOSRecordingRulesSheet().environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Add Keyword Rule"))
    }

    func testShowsSeriesRuleWithChannelAndBadges() async throws {
        let recordingsViewModel = makeRecordingsViewModel()
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{
            "RecordingRuleID":"r1",
            "SeriesID":"s1",
            "Title":"Today Show",
            "ChannelOnly":"4.1",
            "KeywordQuery":"news",
            "TitleMatchMode":"contains",
            "RecentOnly":1,
            "MaxEpisodesToKeep":3,
            "StartPadding":300,
            "EndPadding":600,
            "Provider":"hdhomerun"
        }]
        """.utf8), 200)
        await recordingsViewModel.loadRules()
        let rule = try XCTUnwrap(recordingsViewModel.recordingRules.first)
        XCTAssertTrue(rule.isSeriesRule)

        let view = iOSRecordingRulesSheet().environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Today Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "Series Rule"))
        XCTAssertNoThrow(try view.inspect().find(text: "• Ch 4.1"))
        XCTAssertNoThrow(try view.inspect().find(text: "Keyword: news"))
        XCTAssertNoThrow(try view.inspect().find(text: "Contains match"))
        XCTAssertNoThrow(try view.inspect().find(text: "New only"))
        XCTAssertNoThrow(try view.inspect().find(text: "Keep last 3"))
        XCTAssertNoThrow(try view.inspect().find(text: "Start +5m"))
        XCTAssertNoThrow(try view.inspect().find(text: "End +10m"))
        XCTAssertNoThrow(try view.inspect().find(text: "hdhomerun"))
    }

    func testShowsSingleEpisodeLabelForDateTimeOnlyRuleWithoutBadges() async throws {
        let recordingsViewModel = makeRecordingsViewModel()
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID":"r2","SeriesID":"s2","Title":"Evening News","DateTimeOnly":1700000000}]
        """.utf8), 200)
        await recordingsViewModel.loadRules()
        let rule = try XCTUnwrap(recordingsViewModel.recordingRules.first)
        XCTAssertFalse(rule.isSeriesRule)

        let view = iOSRecordingRulesSheet().environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Evening News"))
        XCTAssertNoThrow(try view.inspect().find(text: "Single Episode"))
        XCTAssertThrowsError(try view.inspect().find(textWhere: { value, _ in value.hasPrefix("• Ch") }))
    }
}
