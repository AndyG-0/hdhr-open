import XCTest
@testable import HDHROpenKit

#if canImport(UIKit)
    /// AVPlayer.allowsExternalPlayback/usesExternalPlaybackWhileExternalScreenIsActive
    /// only exist on iOS/tvOS (Mac Catalyst), not plain macOS - this whole file is a
    /// no-op when `swift test` runs against the host macOS platform (no UIKit); it
    /// only actually exercises anything in an iOS/tvOS simulator test run.
    @MainActor
    final class PlayerEngineExternalPlaybackTests: XCTestCase {
        func test_init_setsAllowsExternalPlayback() {
            let engine = PlayerEngine()
            XCTAssertEqual(engine.avPlayer?.allowsExternalPlayback, true)
        }

        func test_init_setsUsesExternalPlaybackWhileExternalScreenIsActive() {
            let engine = PlayerEngine()
            XCTAssertEqual(engine.avPlayer?.usesExternalPlaybackWhileExternalScreenIsActive, true)
        }

        func test_init_isExternalPlaybackActiveStartsFalse() {
            let engine = PlayerEngine()
            XCTAssertFalse(engine.isExternalPlaybackActive)
        }

        // Real AirPlay route negotiation - toggling isExternalPlaybackActive from
        // an actual external device connecting - has no simulator/CI equivalent
        // and is not covered here; requires manual verification against a real
        // AirPlay-capable device.
    }
#endif
