import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVRecordingDetailViewTests: XCTestCase {
    private func makeRecording(
        title: String = "Morning Show",
        synopsis: String? = "A daily news roundup.",
        recordEnd: TimeInterval? = nil,
        provider: String? = nil
    ) -> HDHomeRunRecording {
        HDHomeRunRecording(
            recordingId: "rec1",
            title: title,
            synopsis: synopsis,
            recordEnd: recordEnd,
            provider: provider
        )
    }

    func testShowsTitleAndSynopsis() throws {
        let view = TVRecordingDetailView(recording: makeRecording(), onPlay: {}, onDelete: {}, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Morning Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "A daily news roundup."))
    }

    func testShowsPlayRecordingLabelWhenNotInProgress() throws {
        let recording = makeRecording(recordEnd: Date().addingTimeInterval(-3600).timeIntervalSince1970)
        let view = TVRecordingDetailView(recording: recording, onPlay: {}, onDelete: {}, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(button: "Play Recording"))
    }

    func testShowsWatchInProgressLabelWhenInProgress() throws {
        let recording = makeRecording(recordEnd: Date().addingTimeInterval(3600).timeIntervalSince1970)
        let view = TVRecordingDetailView(recording: recording, onPlay: {}, onDelete: {}, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(button: "Watch In-Progress"))
    }

    func testHidesDeleteButtonWhenInProgress() throws {
        let recording = makeRecording(recordEnd: Date().addingTimeInterval(3600).timeIntervalSince1970, provider: nil)
        let view = TVRecordingDetailView(recording: recording, onPlay: {}, onDelete: {}, onDismiss: {})

        XCTAssertThrowsError(try view.inspect().find(button: "Delete Recording"))
    }

    func testHidesDeleteButtonWhenHDHomeRunNative() throws {
        let recording = makeRecording(recordEnd: Date().addingTimeInterval(-3600).timeIntervalSince1970, provider: "hdhomerun")
        let view = TVRecordingDetailView(recording: recording, onPlay: {}, onDelete: {}, onDismiss: {})

        XCTAssertThrowsError(try view.inspect().find(button: "Delete Recording"))
    }

    func testShowsDeleteButtonWhenCompletedAndNotHDHomeRunNative() throws {
        let recording = makeRecording(recordEnd: Date().addingTimeInterval(-3600).timeIntervalSince1970, provider: nil)
        let view = TVRecordingDetailView(recording: recording, onPlay: {}, onDelete: {}, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(button: "Delete Recording"))
    }

    func testTappingPlayInvokesOnPlay() throws {
        var played = false
        let view = TVRecordingDetailView(recording: makeRecording(), onPlay: { played = true }, onDelete: {}, onDismiss: {})

        try view.inspect().find(button: "Play Recording").tap()

        XCTAssertTrue(played)
    }

    func testTappingDeleteInvokesOnDelete() throws {
        var deleted = false
        let recording = makeRecording(recordEnd: Date().addingTimeInterval(-3600).timeIntervalSince1970, provider: nil)
        let view = TVRecordingDetailView(recording: recording, onPlay: {}, onDelete: { deleted = true }, onDismiss: {})

        try view.inspect().find(button: "Delete Recording").tap()

        XCTAssertTrue(deleted)
    }

    func testTappingCloseInvokesOnDismiss() throws {
        var dismissed = false
        let view = TVRecordingDetailView(recording: makeRecording(), onPlay: {}, onDelete: {}, onDismiss: { dismissed = true })

        try view.inspect().find(button: "Close").tap()

        XCTAssertTrue(dismissed)
    }
}
