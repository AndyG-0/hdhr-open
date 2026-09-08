#if canImport(UIKit)
    import AVFoundation
    import SwiftUI
    import UIKit
    #if os(iOS)
        import AVKit
    #endif

    /// Renders an `AVPlayer`'s video output via a bare `AVPlayerLayer`, with none
    /// of AVKit's own transport chrome (`VideoPlayer`/`AVPlayerViewController`
    /// always draw their own play/pause/scrub-bar overlay on top of the video).
    /// On tvOS that native overlay is itself focusable and sits over the app's
    /// custom controls (`TVScrubBarView`/`TVPlaybackControlsView`), so the tvOS
    /// focus engine routes the Siri Remote's d-pad into AVKit's own chrome
    /// instead of the app's - the app's controls become permanently unreachable.
    /// Using a plain, non-interactive player layer removes that competing focus
    /// target entirely.
    public struct PlayerLayerView: UIViewRepresentable {
        public let player: AVPlayer

        #if os(iOS)
            /// The engine that should own any `AVPictureInPictureController` built
            /// for this view's `AVPlayerLayer` - `nil` on call sites (or platforms)
            /// that don't want PiP wired up. Optional rather than a tvOS-only
            /// separate initializer so the tvOS call site in `TVPlayerView.swift`
            /// needs no changes.
            public let pictureInPictureEngine: PlayerEngine?

            public init(player: AVPlayer, pictureInPictureEngine: PlayerEngine? = nil) {
                self.player = player
                self.pictureInPictureEngine = pictureInPictureEngine
            }
        #else
            public init(player: AVPlayer) {
                self.player = player
            }
        #endif

        public func makeUIView(context _: Context) -> PlayerLayerContainerView {
            let view = PlayerLayerContainerView()
            view.playerLayer.player = player
            #if os(iOS)
                if let engine = pictureInPictureEngine,
                   AVPictureInPictureController.isPictureInPictureSupported(),
                   let pipController = AVPictureInPictureController(playerLayer: view.playerLayer)
                {
                    engine.attachPictureInPictureController(pipController)
                }
            #endif
            return view
        }

        public func updateUIView(_ uiView: PlayerLayerContainerView, context _: Context) {
            if uiView.playerLayer.player !== player {
                uiView.playerLayer.player = player
            }
        }
    }

    public final class PlayerLayerContainerView: UIView {
        override public static var layerClass: AnyClass {
            AVPlayerLayer.self
        }

        public var playerLayer: AVPlayerLayer {
            // Force-cast is safe: `layerClass` above guarantees `layer` is always
            // backed by an AVPlayerLayer for every instance of this view.
            // swiftlint:disable:next force_cast
            layer as! AVPlayerLayer
        }

        override public init(frame: CGRect) {
            super.init(frame: frame)
            playerLayer.videoGravity = .resizeAspect
        }

        public required init?(coder: NSCoder) {
            super.init(coder: coder)
            playerLayer.videoGravity = .resizeAspect
        }
    }
#endif
