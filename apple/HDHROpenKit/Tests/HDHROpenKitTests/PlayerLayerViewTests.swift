import XCTest
@testable import HDHROpenKit

#if canImport(UIKit)
    import AVFoundation
    import SwiftUI
    import UIKit
    import ViewInspector
    #if os(iOS)
        import AVKit
    #endif

    /// `PlayerLayerView` bridges a bare `AVPlayerLayer` into SwiftUI.
    /// `UIViewRepresentableContext` has no public initializer, so
    /// `makeUIView`/`updateUIView` can't be called in isolation - instead
    /// these tests use ViewInspector's `ViewHosting` to drive the
    /// representable through a real (offscreen) SwiftUI host and inspect the
    /// concrete `PlayerLayerContainerView` it produced. This whole file is a
    /// no-op when `swift test` runs against the host macOS platform (no
    /// UIKit); it only actually exercises anything in an iOS/tvOS simulator
    /// test run.
    @MainActor
    final class PlayerLayerViewTests: XCTestCase {
        func test_makeUIView_assignsPlayerToPlayerLayer() throws {
            let player = AVPlayer()
            #if os(iOS)
                let view = PlayerLayerView(player: player, pictureInPictureEngine: nil)
            #else
                let view = PlayerLayerView(player: player)
            #endif
            ViewHosting.host(view: view)
            defer { ViewHosting.expel() }

            let containerView = try view.uiView()

            XCTAssertTrue(containerView.playerLayer.player === player)
        }

        #if os(iOS)
            func test_makeUIView_withPictureInPictureEngine_stillAssignsPlayer() throws {
                let player = AVPlayer()
                let engine = PlayerEngine()
                let view = PlayerLayerView(player: player, pictureInPictureEngine: engine)
                ViewHosting.host(view: view)
                defer { ViewHosting.expel() }

                let containerView = try view.uiView()

                // Whether a PiP controller actually attaches depends on
                // AVPictureInPictureController.isPictureInPictureSupported(),
                // which varies by simulator/device - only the player wiring
                // (shared with the no-engine path above) is deterministic here.
                XCTAssertTrue(containerView.playerLayer.player === player)
            }
        #endif

        func test_containerView_backingLayerIsAVPlayerLayer() {
            let containerView = PlayerLayerContainerView()

            XCTAssertTrue(containerView.layer is AVPlayerLayer)
            XCTAssertTrue(containerView.playerLayer === containerView.layer)
        }

        func test_containerView_defaultsToResizeAspectVideoGravity() {
            let containerView = PlayerLayerContainerView()

            XCTAssertEqual(containerView.playerLayer.videoGravity, .resizeAspect)
        }

        func test_containerView_startsWithNoPlayerAssigned() {
            let containerView = PlayerLayerContainerView()

            XCTAssertNil(containerView.playerLayer.player)
        }
    }
#endif
