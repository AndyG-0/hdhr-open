import XCTest
@testable import HDHROpenKit

final class CaptionControllerTests: XCTestCase {
    @MainActor
    func testSetCuesFullyReplacesExisting() {
        let controller = CaptionController()
        controller.setCues([CaptionCue(start: 0, end: 1, text: "first")])
        controller.setCues([CaptionCue(start: 5, end: 6, text: "second")])
        XCTAssertEqual(controller.cues.map(\.text), ["second"])
    }

    @MainActor
    func testUpdatePlaybackTimeNoOpWhenDisabled() {
        let controller = CaptionController()
        controller.setCues([CaptionCue(start: 0, end: 5, text: "hello")])
        controller.updatePlaybackTime(2)
        XCTAssertNil(controller.activeCueText)
    }

    @MainActor
    func testUpdatePlaybackTimeActivatesMatchingCue() {
        let controller = CaptionController()
        controller.isEnabled = true
        controller.setCues([
            CaptionCue(start: 0, end: 2, text: "one"),
            CaptionCue(start: 5, end: 7, text: "two")
        ])

        controller.updatePlaybackTime(1)
        XCTAssertEqual(controller.activeCueText, "one")

        controller.updatePlaybackTime(3.5) // gap between cues
        XCTAssertNil(controller.activeCueText)

        controller.updatePlaybackTime(6)
        XCTAssertEqual(controller.activeCueText, "two")
    }

    @MainActor
    func testCueBoundariesInclusive() {
        let controller = CaptionController()
        controller.isEnabled = true
        controller.setCues([CaptionCue(start: 1, end: 2, text: "hello")])

        controller.updatePlaybackTime(1)
        XCTAssertEqual(controller.activeCueText, "hello")

        controller.updatePlaybackTime(2)
        XCTAssertEqual(controller.activeCueText, "hello")
    }

    @MainActor
    func testToggleEnabledClearsActiveCueAndDoesNotAutoRecomputeOnReEnable() {
        let controller = CaptionController()
        controller.isEnabled = true
        controller.setCues([CaptionCue(start: 0, end: 5, text: "hello")])
        controller.updatePlaybackTime(1)
        XCTAssertEqual(controller.activeCueText, "hello")

        controller.isEnabled = false
        XCTAssertNil(controller.activeCueText)

        controller.isEnabled = true
        XCTAssertNil(controller.activeCueText) // no auto-recompute from last known time
    }

    @MainActor
    func testResetClearsCuesAndActiveTextButPreservesEnabledState() {
        let controller = CaptionController()
        controller.isEnabled = true
        controller.setCues([CaptionCue(start: 0, end: 5, text: "hello")])
        controller.updatePlaybackTime(1)
        XCTAssertEqual(controller.activeCueText, "hello")

        controller.reset()

        XCTAssertTrue(controller.cues.isEmpty)
        XCTAssertNil(controller.activeCueText)
        XCTAssertTrue(controller.isEnabled)
    }
}
