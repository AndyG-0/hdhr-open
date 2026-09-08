import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVPlayerRecordMenuOverlayTests: XCTestCase {
    private func makeRule() -> HDHomeRunRecordingRule {
        HDHomeRunRecordingRule(recordingRuleId: "1", seriesId: "s1", title: "Show")
    }

    func testShowsCancelRecordingSectionWhenRuleExists() throws {
        let view = TVPlayerRecordMenuOverlay(
            existingRule: makeRule(),
            canRecordSeries: true,
            isPromoted: false,
            isPromoting: false,
            onSaveCurrentRecording: {},
            onRecordEpisode: {},
            onRecordSeries: {},
            onCancelRule: {},
            onOptions: {},
            onDismiss: {}
        )

        XCTAssertNoThrow(try view.inspect().find(text: "Cancel Recording"))
        XCTAssertNoThrow(try view.inspect().find(text: "Recording Options…"))
        XCTAssertThrowsError(try view.inspect().find(text: "Save Current Recording"))
        XCTAssertThrowsError(try view.inspect().find(text: "Record Episode"))
    }

    func testShowsSaveAndRecordSectionWhenNoExistingRule() throws {
        let view = TVPlayerRecordMenuOverlay(
            existingRule: nil,
            canRecordSeries: false,
            isPromoted: false,
            isPromoting: false,
            onSaveCurrentRecording: {},
            onRecordEpisode: {},
            onRecordSeries: {},
            onCancelRule: {},
            onOptions: {},
            onDismiss: {}
        )

        XCTAssertNoThrow(try view.inspect().find(text: "Save Current Recording"))
        XCTAssertNoThrow(try view.inspect().find(text: "Record Episode"))
        XCTAssertThrowsError(try view.inspect().find(text: "Cancel Recording"))
        XCTAssertThrowsError(try view.inspect().find(text: "Record Series"))
    }

    func testShowsRecordSeriesOptionWhenCanRecordSeries() throws {
        let view = TVPlayerRecordMenuOverlay(
            existingRule: nil,
            canRecordSeries: true,
            isPromoted: false,
            isPromoting: false,
            onSaveCurrentRecording: {},
            onRecordEpisode: {},
            onRecordSeries: {},
            onCancelRule: {},
            onOptions: {},
            onDismiss: {}
        )

        XCTAssertNoThrow(try view.inspect().find(text: "Record Series"))
    }

    func testShowsRecordingSavedLabelWhenPromoted() throws {
        let view = TVPlayerRecordMenuOverlay(
            existingRule: nil,
            canRecordSeries: false,
            isPromoted: true,
            isPromoting: false,
            onSaveCurrentRecording: {},
            onRecordEpisode: {},
            onRecordSeries: {},
            onCancelRule: {},
            onOptions: {},
            onDismiss: {}
        )

        XCTAssertNoThrow(try view.inspect().find(text: "Recording Saved"))
        XCTAssertTrue(try view.inspect().find(button: "Recording Saved").isDisabled())
    }

    func testSaveButtonDisabledWhilePromoting() throws {
        let view = TVPlayerRecordMenuOverlay(
            existingRule: nil,
            canRecordSeries: false,
            isPromoted: false,
            isPromoting: true,
            onSaveCurrentRecording: {},
            onRecordEpisode: {},
            onRecordSeries: {},
            onCancelRule: {},
            onOptions: {},
            onDismiss: {}
        )

        XCTAssertTrue(try view.inspect().find(button: "Save Current Recording").isDisabled())
    }

    func testTappingCloseInvokesOnDismiss() throws {
        var dismissed = false
        let view = TVPlayerRecordMenuOverlay(
            existingRule: nil,
            canRecordSeries: false,
            isPromoted: false,
            isPromoting: false,
            onSaveCurrentRecording: {},
            onRecordEpisode: {},
            onRecordSeries: {},
            onCancelRule: {},
            onOptions: {},
            onDismiss: { dismissed = true }
        )

        try view.inspect().find(button: "Close").tap()

        XCTAssertTrue(dismissed)
    }

    func testTappingCancelRecordingInvokesOnCancelRule() throws {
        var cancelled = false
        let view = TVPlayerRecordMenuOverlay(
            existingRule: makeRule(),
            canRecordSeries: false,
            isPromoted: false,
            isPromoting: false,
            onSaveCurrentRecording: {},
            onRecordEpisode: {},
            onRecordSeries: {},
            onCancelRule: { cancelled = true },
            onOptions: {},
            onDismiss: {}
        )

        try view.inspect().find(button: "Cancel Recording").tap()

        XCTAssertTrue(cancelled)
    }

    func testTappingSaveCurrentRecordingInvokesCallback() throws {
        var saved = false
        let view = TVPlayerRecordMenuOverlay(
            existingRule: nil,
            canRecordSeries: false,
            isPromoted: false,
            isPromoting: false,
            onSaveCurrentRecording: { saved = true },
            onRecordEpisode: {},
            onRecordSeries: {},
            onCancelRule: {},
            onOptions: {},
            onDismiss: {}
        )

        try view.inspect().find(button: "Save Current Recording").tap()

        XCTAssertTrue(saved)
    }
}
