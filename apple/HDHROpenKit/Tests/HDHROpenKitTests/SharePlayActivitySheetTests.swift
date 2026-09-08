import XCTest
@testable import HDHROpenKit

#if os(iOS)
    import GroupActivities
    import SwiftUI
    import UIKit
    import ViewInspector

    /// `SharePlayActivitySheet` wraps `GroupActivitySharingController`'s
    /// system sheet - iOS/Mac Catalyst only, see the source file's doc
    /// comment. This whole file is a no-op when `swift test` runs against
    /// the host macOS platform (not `os(iOS)`); it only actually exercises
    /// anything in an iOS simulator test run.
    @MainActor
    final class SharePlayActivitySheetTests: XCTestCase {
        func test_init_storesActivity() {
            let activity = WatchProgramActivity(channelNumber: "5.1", title: "Local News")
            let sheet = SharePlayActivitySheet(activity: activity)

            XCTAssertEqual(sheet.activity.channelNumber, "5.1")
            XCTAssertEqual(sheet.activity.title, "Local News")
            XCTAssertNil(sheet.activity.recordingId)
        }

        func test_init_defaultOnDismissIsNil() {
            let activity = WatchProgramActivity(channelNumber: "5.1", title: "Local News")
            let sheet = SharePlayActivitySheet(activity: activity)

            XCTAssertNil(sheet.onDismiss)
        }

        func test_init_storesProvidedOnDismiss() {
            let activity = WatchProgramActivity(channelNumber: "5.1", title: "Local News")
            var called = false
            let sheet = SharePlayActivitySheet(activity: activity) { called = true }

            XCTAssertNotNil(sheet.onDismiss)
            sheet.onDismiss?()
            XCTAssertTrue(called)
        }

        /// On the Simulator/CI - no FaceTime/iCloud sign-in, no active call -
        /// `GroupActivitySharingController(activity)` reliably fails to
        /// construct (see the source file's doc comment), so
        /// `makeUIViewController` takes its guard-failure branch: return a
        /// bare `UIViewController` and invoke `onDismiss` asynchronously.
        /// That's the one branch this environment can exercise
        /// deterministically; the success branch needs a real device in a
        /// live FaceTime call.
        func test_makeUIViewController_whenSharingControllerUnavailable_returnsPlainControllerAndDismisses() throws {
            let activity = WatchProgramActivity(channelNumber: "5.1", title: "Local News")
            let dismissExpectation = expectation(description: "onDismiss called")
            let sheet = SharePlayActivitySheet(activity: activity) {
                dismissExpectation.fulfill()
            }

            ViewHosting.host(view: sheet)
            defer { ViewHosting.expel() }

            let controller = try sheet.viewController()
            XCTAssertFalse(controller is GroupActivitySharingController)

            wait(for: [dismissExpectation], timeout: 5)
        }
    }
#endif
