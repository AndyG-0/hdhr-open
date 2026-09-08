import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVProgramDetailModalTests: XCTestCase {
    private func makeEnvironmentObjects() -> (GuideViewModel, RecordingsViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let recordingsViewModel = RecordingsViewModel(apiClient: apiClient)
        return (guideViewModel, recordingsViewModel)
    }

    private func makeChannel(number: String = "5.1", isHD: Bool = false) -> HDHomeRunChannel {
        HDHomeRunChannel(channelNumber: number, name: "WXYZ", isHD: isHD)
    }

    private func makeAiring(offsetMinutes: Double = 60, durationMinutes: Double = 30) -> HDHomeRunGuideEntry {
        let now = Date().timeIntervalSince1970
        return HDHomeRunGuideEntry(
            seriesId: "SH123",
            title: "Morning Show",
            episodeTitle: "The Pilot",
            start: now + offsetMinutes * 60,
            end: now + (offsetMinutes + durationMinutes) * 60,
            channelNumber: "5.1"
        )
    }

    private func makeRule(id: String = "rule1", isSeries: Bool = true) -> HDHomeRunRecordingRule {
        HDHomeRunRecordingRule(
            recordingRuleId: id,
            seriesId: "SH123",
            title: "Morning Show",
            dateTimeOnly: isSeries ? nil : Date().timeIntervalSince1970
        )
    }

    private struct Flags {
        var watch = false
        var recordEpisode = false
        var recordSeries = false
        var cancelledRuleId: String?
        var toggledFavorite = false
        var dismissed = false
        var addedToMultiView = false
    }

    private func makeView(
        channel: HDHomeRunChannel,
        airing: HDHomeRunGuideEntry,
        existingRule: HDHomeRunRecordingRule?,
        isFavorite: Bool,
        guideViewModel _: GuideViewModel,
        recordingsViewModel _: RecordingsViewModel,
        includeMultiView: Bool = false,
        flags: @escaping (Flags) -> Void
    ) -> TVProgramDetailModal {
        var state = Flags()
        return TVProgramDetailModal(
            channel: channel,
            airing: airing,
            existingRule: existingRule,
            isFavorite: isFavorite,
            onWatch: { state.watch = true; flags(state) },
            onRecordEpisode: { state.recordEpisode = true; flags(state) },
            onRecordSeries: { state.recordSeries = true; flags(state) },
            onCancelRule: { id in state.cancelledRuleId = id; flags(state) },
            onToggleFavorite: { state.toggledFavorite = true; flags(state) },
            onDismiss: { state.dismissed = true; flags(state) },
            onAddToMultiView: includeMultiView ? { state.addedToMultiView = true; flags(state) } : nil
        )
    }

    func testShowsChannelAndAiringInfo() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            flags: { _ in }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "5.1"))
        XCTAssertNoThrow(try view.inspect().find(text: "WXYZ"))
        XCTAssertNoThrow(try view.inspect().find(text: "Morning Show"))
    }

    func testShowsWatchLiveButtonWhenCurrentlyAiring() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(offsetMinutes: -10, durationMinutes: 30),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            flags: { _ in }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Watch Live"))
    }

    func testHidesWatchLiveButtonWhenNotCurrentlyAiring() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(offsetMinutes: 60, durationMinutes: 30),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            flags: { _ in }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(button: "Watch Live"))
    }

    func testShowsRecordButtonsWhenNoExistingRule() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            flags: { _ in }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Record Episode"))
        XCTAssertNoThrow(try view.inspect().find(button: "Record Series"))
        XCTAssertThrowsError(try view.inspect().find(button: "Cancel Recording"))
    }

    func testShowsCancelRecordingButtonWhenExistingRuleExists() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(),
            existingRule: makeRule(),
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            flags: { _ in }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Cancel Recording"))
        XCTAssertThrowsError(try view.inspect().find(button: "Record Episode"))
        XCTAssertThrowsError(try view.inspect().find(button: "Record Series"))
    }

    func testShowsFavoriteStarInHeaderWhenIsFavorite() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(),
            existingRule: nil,
            isFavorite: true,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            flags: { _ in }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Unfavorite Channel"))
    }

    func testShowsFavoriteChannelButtonLabelWhenNotFavorite() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            flags: { _ in }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Favorite Channel"))
    }

    func testTappingCloseButtonInvokesOnDismiss() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        var dismissed = false
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            flags: { state in dismissed = state.dismissed }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        try view.inspect().find(button: "Close").tap()

        XCTAssertTrue(dismissed)
    }

    func testTappingRecordEpisodeInvokesOnRecordEpisode() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        var recorded = false
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            flags: { state in recorded = state.recordEpisode }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        try view.inspect().find(button: "Record Episode").tap()

        XCTAssertTrue(recorded)
    }

    func testShowsAddToMultiViewButtonWhenLiveAndHandlerProvided() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        var added = false
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(offsetMinutes: -10, durationMinutes: 30),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            includeMultiView: true,
            flags: { state in added = state.addedToMultiView }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        let button = try view.inspect().find(button: "Add to Multi-View")
        XCTAssertNoThrow(button)
        try button.tap()
        XCTAssertTrue(added)
    }

    func testHidesAddToMultiViewButtonWhenNotLive() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(offsetMinutes: 60, durationMinutes: 30),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            includeMultiView: true,
            flags: { _ in }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(button: "Add to Multi-View"))
    }

    func testTwoRowActionButtonsRenderAllActionsSimultaneously() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(
            channel: makeChannel(),
            airing: makeAiring(offsetMinutes: -10, durationMinutes: 30),
            existingRule: nil,
            isFavorite: false,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            includeMultiView: true,
            flags: { _ in }
        )
        .environmentObject(guideViewModel)
        .environmentObject(recordingsViewModel)

        // Row 1 buttons (Playback & recording creation)
        XCTAssertNoThrow(try view.inspect().find(button: "Watch Live"))
        XCTAssertNoThrow(try view.inspect().find(button: "Add to Multi-View"))
        XCTAssertNoThrow(try view.inspect().find(button: "Record Episode"))
        XCTAssertNoThrow(try view.inspect().find(button: "Record Series"))

        // Row 2 buttons (Options, favorite toggle, and close)
        XCTAssertNoThrow(try view.inspect().find(button: "Options…"))
        XCTAssertNoThrow(try view.inspect().find(button: "Favorite Channel"))
        XCTAssertNoThrow(try view.inspect().find(button: "Close"))
    }
}
