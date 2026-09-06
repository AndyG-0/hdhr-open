import XCTest
import AVKit
@testable import HDHROpenKit

#if os(iOS)
// AVPictureInPictureController and its delegate protocol are iOS-only (not
// available on tvOS or the bare macOS host `swift test` runs against) - this
// whole file is a no-op outside an iOS simulator/device test run.
@MainActor
final class PlayerEnginePictureInPictureTests: XCTestCase {
    func test_init_isPictureInPictureActiveStartsFalse() {
        let engine = PlayerEngine()
        XCTAssertFalse(engine.isPictureInPictureActive)
    }

    func test_init_isPictureInPictureSupportedMatchesSystemCapability() {
        let engine = PlayerEngine()
        XCTAssertEqual(engine.isPictureInPictureSupported, AVPictureInPictureController.isPictureInPictureSupported())
    }

    func test_togglePictureInPicture_withoutAttachedControllerIsNoOp() {
        let engine = PlayerEngine()
        engine.togglePictureInPicture()
        XCTAssertFalse(engine.isPictureInPictureActive)
    }

    // Real PiP start/stop requires an AVPlayerLayer actually attached to a
    // live window plus the system compositor/foreground-background
    // transition - none of which has a simulator/CI equivalent.
    // `restoreUserInterfaceForPictureInPictureStop` and the
    // HDHROpeniOSApp scenePhase background-survival exception are
    // likewise not covered here; requires manual verification against a
    // real device.
}
#endif
