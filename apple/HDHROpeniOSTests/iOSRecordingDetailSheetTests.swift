import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSRecordingDetailSheetTests: XCTestCase {
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

    func testShowsTitleEpisodeAndMetadataBadges() throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        let recording = HDHomeRunRecording(
            title: "Today Show",
            episodeTitle: "Pilot",
            seasonNumber: 1,
            episodeNumber: "2",
            synopsis: "A morning news program.",
            durationSeconds: 3665,
            fileSizeBytes: 2_147_483_648
        )

        let view = iOSRecordingDetailSheet(recording: recording)
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Today Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "Pilot"))
        XCTAssertNoThrow(try view.inspect().find(text: "S1:E2"))
        XCTAssertNoThrow(try view.inspect().find(text: "1h 1m"))
        XCTAssertNoThrow(try view.inspect().find(text: "2.0 GB"))
        XCTAssertNoThrow(try view.inspect().find(text: "A morning news program."))
    }

    func testHidesEpisodeTitleAndSynopsisWhenNil() throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        let recording = HDHomeRunRecording(title: "Standalone Movie")

        let view = iOSRecordingDetailSheet(recording: recording)
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Standalone Movie"))
        XCTAssertThrowsError(try view.inspect().find(ViewType.Text.self, where: { try $0.string() == "Pilot" }))
    }

    func testShowsWatchInProgressLabelWhenRecordingIsInProgress() throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        let recording = HDHomeRunRecording(title: "Live Game", recordEnd: Date().timeIntervalSince1970 + 1800)
        XCTAssertTrue(recording.isInProgress)

        let view = iOSRecordingDetailSheet(recording: recording)
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Watch In-Progress"))
        XCTAssertThrowsError(try view.inspect().find(button: "Play Recording"))
    }

    func testShowsPlayRecordingLabelWhenNotInProgress() throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        let recording = HDHomeRunRecording(title: "Finished Show", recordEnd: Date().timeIntervalSince1970 - 1800)
        XCTAssertFalse(recording.isInProgress)

        let view = iOSRecordingDetailSheet(recording: recording)
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Play Recording"))
        XCTAssertThrowsError(try view.inspect().find(button: "Watch In-Progress"))
    }

    func testHidesDeleteButtonForHDHomeRunNativeRecording() throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        let recording = HDHomeRunRecording(title: "Native Recording", provider: "hdhomerun")
        XCTAssertTrue(recording.isHDHomeRunNative)

        let view = iOSRecordingDetailSheet(recording: recording)
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "HDHomeRun DVR"))
        XCTAssertThrowsError(try view.inspect().find(button: "Delete Recording"))
    }

    func testShowsDeleteButtonForNonNativeRecording() throws {
        let (recordingsViewModel, playerViewModel) = makeEnvironmentObjects()
        let recording = HDHomeRunRecording(title: "Local Recording")
        XCTAssertFalse(recording.isHDHomeRunNative)

        let view = iOSRecordingDetailSheet(recording: recording)
            .environmentObject(recordingsViewModel)
            .environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Built-in"))
        XCTAssertNoThrow(try view.inspect().find(button: "Delete Recording"))
    }
}
