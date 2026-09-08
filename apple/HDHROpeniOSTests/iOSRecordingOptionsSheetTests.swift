import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSRecordingOptionsSheetTests: XCTestCase {
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

    private let channel = HDHomeRunChannel(channelNumber: "4.1", name: "WNBC", isHD: true)
    private let airing = HDHomeRunGuideEntry(title: "Today Show", start: 1_700_000_000)

    private func makeSheet(
        canRecordSeries: Bool = true,
        existingRule: HDHomeRunRecordingRule? = nil,
        onConfirm: @escaping (Bool, RecordingRuleOptions) -> Void = { _, _ in },
        onCancelRule: (() -> Void)? = nil
    ) -> iOSRecordingOptionsSheet {
        iOSRecordingOptionsSheet(
            channel: channel,
            airing: airing,
            canRecordSeries: canRecordSeries,
            existingRule: existingRule,
            onConfirm: onConfirm,
            onCancelRule: onCancelRule
        )
    }

    func testShowsEpisodeAndSeriesButtonsWhenNoExistingRule() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeSheet()
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Record Episode"))
        XCTAssertNoThrow(try view.inspect().find(button: "Record Series"))
        XCTAssertThrowsError(try view.inspect().find(button: "Cancel Recording"))
    }

    func testHidesSeriesButtonWhenCanRecordSeriesFalse() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeSheet(canRecordSeries: false)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Record Episode"))
        XCTAssertThrowsError(try view.inspect().find(button: "Record Series"))
    }

    func testShowsUpdateSeriesAndCancelButtonsForExistingSeriesRule() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let rule = HDHomeRunRecordingRule(recordingRuleId: "r1", seriesId: "s1", title: "Today Show")
        XCTAssertTrue(rule.isSeriesRule)

        let view = makeSheet(existingRule: rule, onCancelRule: {})
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Update Series Recording"))
        XCTAssertNoThrow(try view.inspect().find(button: "Cancel Recording"))
        XCTAssertThrowsError(try view.inspect().find(button: "Record Episode"))
    }

    func testShowsUpdateEpisodeButtonForExistingEpisodeRule() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let rule = HDHomeRunRecordingRule(recordingRuleId: "r1", seriesId: "s1", title: "Today Show", dateTimeOnly: 1_700_000_000)
        XCTAssertFalse(rule.isSeriesRule)

        let view = makeSheet(existingRule: rule)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Update Episode Recording"))
    }

    func testShowsKeywordFooterWhenExistingRuleUsesContainsMatch() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let rule = HDHomeRunRecordingRule(recordingRuleId: "r1", seriesId: "s1", title: "Today Show", titleMatchMode: "contains")

        let view = makeSheet(existingRule: rule)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Keyword and contains-match rules always record via the built-in DVR."))
    }

    func testHidesKeywordFooterByDefault() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeSheet()
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Keyword and contains-match rules always record via the built-in DVR."))
    }

    func testShowsOfficialDvrFooterAndHidesRetentionPickerWhenTargetingOfficialDvr() async throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/dvr/info"] = (Data("""
        {"friendly_name":"HDHomeRun RECORD","is_builtin":false}
        """.utf8), 200)
        await recordingsViewModel.loadDvrInfo()
        XCTAssertEqual(recordingsViewModel.dvrInfo?.isBuiltin, false)

        let view = makeSheet()
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Retention is managed by the official HDHomeRun DVR."))
        XCTAssertThrowsError(try view.inspect().find(text: "Unlimited"))
    }

    func testShowsRetentionPickerByDefaultWhenNotTargetingOfficialDvr() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertNil(recordingsViewModel.dvrInfo)

        let view = makeSheet()
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Unlimited"))
        XCTAssertThrowsError(try view.inspect().find(text: "Retention is managed by the official HDHomeRun DVR."))
    }

    func testShowsCustomChannelSelectionWhenExistingRuleHasMultipleChannels() async throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels":[
            {"channel_number":"4.1","name":"WNBC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null},
            {"channel_number":"5.1","name":"WABC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null}
        ],"guide_available":true}
        """.utf8), 200)
        await guideViewModel.loadChannels()

        let rule = HDHomeRunRecordingRule(recordingRuleId: "r1", seriesId: "s1", title: "Today Show", channelOnly: "4.1|5.1")

        let view = makeSheet(existingRule: rule)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "4.1 WNBC"))
        XCTAssertNoThrow(try view.inspect().find(text: "5.1 WABC"))
    }

    func testTappingRecordEpisodeInvokesOnConfirmWithFalse() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        var confirmedRecordSeries: Bool?
        var confirmedOptions: RecordingRuleOptions?

        let view = makeSheet(onConfirm: { recordSeries, options in
            confirmedRecordSeries = recordSeries
            confirmedOptions = options
        })
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        try view.inspect().find(button: "Record Episode").tap()

        XCTAssertEqual(confirmedRecordSeries, false)
        XCTAssertEqual(confirmedOptions?.title, "Today Show")
    }

    func testTappingCancelRecordingInvokesOnCancelRule() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        var cancelled = false
        let rule = HDHomeRunRecordingRule(recordingRuleId: "r1", seriesId: "s1", title: "Today Show")

        let view = makeSheet(existingRule: rule, onCancelRule: { cancelled = true })
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        try view.inspect().find(button: "Cancel Recording").tap()

        XCTAssertTrue(cancelled)
    }
}
