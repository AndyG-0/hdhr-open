import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVRecordingOptionsModalTests: XCTestCase {
    private func makeEnvironmentObjects() -> (GuideViewModel, RecordingsViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let recordingsViewModel = RecordingsViewModel(apiClient: apiClient)
        return (guideViewModel, recordingsViewModel)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    private func makeChannel() -> HDHomeRunChannel {
        HDHomeRunChannel(channelNumber: "5.1", name: "WXYZ")
    }

    private func makeAiring(episodeTitle: String? = "The Pilot") -> HDHomeRunGuideEntry {
        HDHomeRunGuideEntry(seriesId: "SH123", title: "Morning Show", episodeTitle: episodeTitle, channelNumber: "5.1")
    }

    func testShowsRecordEpisodeAndSeriesButtonsWhenNoExistingRule() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(),
            canRecordSeries: true,
            existingRule: nil,
            onConfirm: { _, _ in },
            onCancelRule: nil
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Record Episode"))
        XCTAssertNoThrow(try view.inspect().find(button: "Record Series"))
    }

    func testHidesRecordSeriesButtonWhenCanRecordSeriesFalse() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(),
            canRecordSeries: false,
            existingRule: nil,
            onConfirm: { _, _ in },
            onCancelRule: nil
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Record Episode"))
        XCTAssertThrowsError(try view.inspect().find(button: "Record Series"))
    }

    func testShowsUpdateSeriesButtonWhenExistingSeriesRuleExists() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let rule = HDHomeRunRecordingRule(recordingRuleId: "r1", seriesId: "SH123", title: "Morning Show", dateTimeOnly: nil)
        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(),
            canRecordSeries: true,
            existingRule: rule,
            onConfirm: { _, _ in },
            onCancelRule: {}
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Update Series Recording"))
        XCTAssertNoThrow(try view.inspect().find(button: "Cancel Recording"))
    }

    func testShowsUpdateEpisodeButtonWhenExistingEpisodeRuleExists() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "r1",
            seriesId: "SH123",
            title: "Morning Show",
            dateTimeOnly: Date().timeIntervalSince1970
        )
        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(),
            canRecordSeries: true,
            existingRule: rule,
            onConfirm: { _, _ in },
            onCancelRule: {}
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Update Episode Recording"))
    }

    func testHidesCancelRecordingButtonWhenOnCancelRuleNil() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let rule = HDHomeRunRecordingRule(recordingRuleId: "r1", seriesId: "SH123", title: "Morning Show", dateTimeOnly: nil)
        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(),
            canRecordSeries: true,
            existingRule: rule,
            onConfirm: { _, _ in },
            onCancelRule: nil
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(button: "Cancel Recording"))
    }

    func testShowsRetentionSectionByDefault() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertNil(recordingsViewModel.dvrInfo)

        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(),
            canRecordSeries: true,
            existingRule: nil,
            onConfirm: { _, _ in },
            onCancelRule: nil
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Keep Episodes"))
    }

    func testHidesRetentionSectionWhenOfficialDvrIsTarget() async throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/dvr/info"] = (Data("""
        {"friendly_name":"HDHomeRun DVR","is_builtin":false}
        """.utf8), 200)
        await recordingsViewModel.loadDvrInfo()
        XCTAssertEqual(recordingsViewModel.dvrInfo?.isBuiltin, false)

        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(),
            canRecordSeries: true,
            existingRule: nil,
            onConfirm: { _, _ in },
            onCancelRule: nil
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Keep Episodes"))
        XCTAssertNoThrow(try view.inspect().find(text: "Retention is managed by the official HDHomeRun DVR."))
    }

    func testShowsKeywordSuggestionButtonForEpisodeTitle() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(episodeTitle: "The Pilot"),
            canRecordSeries: true,
            existingRule: nil,
            onConfirm: { _, _ in },
            onCancelRule: nil
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "+ Use \"The Pilot\" as keyword"))
    }

    func testHidesKeywordSuggestionButtonWhenNoEpisodeTitle() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(episodeTitle: nil),
            canRecordSeries: true,
            existingRule: nil,
            onConfirm: { _, _ in },
            onCancelRule: nil
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(ViewType.Button.self, containing: "as keyword"))
    }

    func testTappingRecordEpisodeInvokesOnConfirmWithEpisodeOptions() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        var confirmedIsSeries: Bool?
        var confirmedOptions: RecordingRuleOptions?
        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(),
            canRecordSeries: true,
            existingRule: nil,
            onConfirm: { isSeries, options in
                confirmedIsSeries = isSeries
                confirmedOptions = options
            },
            onCancelRule: nil
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        try view.inspect().find(button: "Record Episode").tap()

        XCTAssertEqual(confirmedIsSeries, false)
        XCTAssertEqual(confirmedOptions?.title, "Morning Show")
    }

    func testTappingCancelRecordingInvokesOnCancelRule() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let rule = HDHomeRunRecordingRule(recordingRuleId: "r1", seriesId: "SH123", title: "Morning Show", dateTimeOnly: nil)
        var cancelled = false
        let view = TVRecordingOptionsModal(
            channel: makeChannel(),
            airing: makeAiring(),
            canRecordSeries: true,
            existingRule: rule,
            onConfirm: { _, _ in },
            onCancelRule: { cancelled = true }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        try view.inspect().find(button: "Cancel Recording").tap()

        XCTAssertTrue(cancelled)
    }
}
