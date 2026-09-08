import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVRecordingCardViewTests: XCTestCase {
    private func makeRecording(
        title: String = "Morning Show",
        episodeTitle: String? = "The Pilot",
        recordEnd: TimeInterval? = nil,
        episodeNumber: String? = "3",
        seasonNumber: Int? = 1,
        durationSeconds: Double? = 3600,
        fileSizeBytes: Int64? = 2_147_483_648,
        provider: String? = "hdhomerun"
    ) -> HDHomeRunRecording {
        HDHomeRunRecording(
            recordingId: "rec1",
            title: title,
            episodeTitle: episodeTitle,
            seasonNumber: seasonNumber,
            episodeNumber: episodeNumber,
            recordEnd: recordEnd,
            durationSeconds: durationSeconds,
            fileSizeBytes: fileSizeBytes,
            provider: provider
        )
    }

    func testShowsTitleAndEpisodeTitle() throws {
        let view = TVRecordingCardView(recording: makeRecording()) {}

        XCTAssertNoThrow(try view.inspect().find(text: "Morning Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "The Pilot"))
    }

    func testShowsRecordingBadgeWhenInProgress() throws {
        let recording = makeRecording(recordEnd: Date().addingTimeInterval(3600).timeIntervalSince1970)
        XCTAssertTrue(recording.isInProgress)
        let view = TVRecordingCardView(recording: recording) {}

        XCTAssertNoThrow(try view.inspect().find(text: "RECORDING"))
    }

    func testHidesRecordingBadgeWhenCompleted() throws {
        let recording = makeRecording(recordEnd: Date().addingTimeInterval(-3600).timeIntervalSince1970)
        XCTAssertFalse(recording.isInProgress)
        let view = TVRecordingCardView(recording: recording) {}

        XCTAssertThrowsError(try view.inspect().find(text: "RECORDING"))
    }

    func testShowsHDHomeRunDvrLabelWhenNative() throws {
        let recording = makeRecording(provider: "hdhomerun")
        let view = TVRecordingCardView(recording: recording) {}

        XCTAssertNoThrow(try view.inspect().find(text: "HDHomeRun DVR"))
    }

    func testShowsBuiltinLabelWhenNotNative() throws {
        let recording = makeRecording(provider: nil)
        let view = TVRecordingCardView(recording: recording) {}

        XCTAssertNoThrow(try view.inspect().find(text: "Built-in"))
    }

    func testShowsEpisodeDesignationAndDuration() throws {
        let recording = makeRecording()
        let view = TVRecordingCardView(recording: recording) {}

        XCTAssertNoThrow(try view.inspect().find(text: "S1:E3"))
        XCTAssertNoThrow(try view.inspect().find(text: "1h 0m"))
    }

    func testTappingCardInvokesOnSelect() throws {
        var didSelect = false
        let view = TVRecordingCardView(recording: makeRecording()) { didSelect = true }

        try view.inspect().find(ViewType.Button.self).tap()

        XCTAssertTrue(didSelect)
    }
}
