import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSProgramDetailSheetTests: XCTestCase {
    private func makeEnvironmentObjects() -> (GuideViewModel, PlayerViewModel, RecordingsViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let recordingsViewModel = RecordingsViewModel(apiClient: apiClient)
        return (guideViewModel, playerViewModel, recordingsViewModel)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    private let channel = HDHomeRunChannel(channelNumber: "4.1", name: "WNBC", isHD: true)

    func testShowsAiringDetailsAndBadges() throws {
        let (guideViewModel, playerViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let now = Date().timeIntervalSince1970
        let airing = HDHomeRunGuideEntry(
            title: "Today Show",
            episodeTitle: "Pilot",
            episodeNumber: "2",
            seasonNumber: 1,
            synopsis: "A morning news program.",
            start: now - 1800,
            end: now + 1800,
            originalAirdate: "2020-01-01",
            category: "Drama, Comedy",
            isNew: true,
            hasCC: true,
            audio: "5.1"
        )

        let view = iOSProgramDetailSheet(channel: channel, airing: airing)
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "4.1"))
        XCTAssertNoThrow(try view.inspect().find(text: "WNBC"))
        XCTAssertNoThrow(try view.inspect().find(text: "Today Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "S1E2 • Pilot"))
        XCTAssertNoThrow(try view.inspect().find(text: "A morning news program."))
        XCTAssertNoThrow(try view.inspect().find(text: "CC"))
        XCTAssertNoThrow(try view.inspect().find(text: "NEW"))
        XCTAssertNoThrow(try view.inspect().find(text: "5.1"))
        XCTAssertNoThrow(try view.inspect().find(text: "Drama"))
        XCTAssertNoThrow(try view.inspect().find(text: "Original Air Date: 2020-01-01"))
    }

    func testHidesCCBadgeWhenHasCCIsFalse() throws {
        let (guideViewModel, playerViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let airing = HDHomeRunGuideEntry(title: "No Captions Show", hasCC: false)

        let view = iOSProgramDetailSheet(channel: channel, airing: airing)
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "CC"))
    }

    func testShowsWatchLiveButtonWhenCurrentlyAiring() throws {
        let (guideViewModel, playerViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let now = Date().timeIntervalSince1970
        let airing = HDHomeRunGuideEntry(title: "Live Now", start: now - 600, end: now + 600)

        let view = iOSProgramDetailSheet(channel: channel, airing: airing)
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Watch Live"))
    }

    func testHidesWatchLiveButtonWhenNotCurrentlyAiring() throws {
        let (guideViewModel, playerViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let now = Date().timeIntervalSince1970
        let airing = HDHomeRunGuideEntry(title: "Later Show", start: now + 3600, end: now + 7200)

        let view = iOSProgramDetailSheet(channel: channel, airing: airing)
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(button: "Watch Live"))
    }

    func testShowsRecordButtonsWhenNoExistingRule() throws {
        let (guideViewModel, playerViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let airing = HDHomeRunGuideEntry(title: "Some Show")
        XCTAssertNil(guideViewModel.findRule(for: channel.channelNumber, airing: airing))

        let view = iOSProgramDetailSheet(channel: channel, airing: airing)
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Record Episode"))
        XCTAssertNoThrow(try view.inspect().find(button: "Record Series"))
        XCTAssertThrowsError(try view.inspect().find(button: "Cancel Recording"))
    }

    func testShowsCancelRecordingButtonWhenRuleExists() async throws {
        let (guideViewModel, playerViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let airing = HDHomeRunGuideEntry(title: "Recurring Show")

        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID":"r1","SeriesID":"s1","Title":"Recurring Show"}]
        """.utf8), 200)
        await guideViewModel.loadRules()
        XCTAssertNotNil(guideViewModel.findRule(for: channel.channelNumber, airing: airing))

        let view = iOSProgramDetailSheet(channel: channel, airing: airing)
            .environmentObject(guideViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Cancel Recording"))
        XCTAssertThrowsError(try view.inspect().find(button: "Record Episode"))
        XCTAssertThrowsError(try view.inspect().find(button: "Record Series"))
    }
}
