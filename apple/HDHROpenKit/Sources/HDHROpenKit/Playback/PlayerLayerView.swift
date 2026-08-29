#if canImport(UIKit)
import SwiftUI
import AVFoundation
import UIKit

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

    public init(player: AVPlayer) {
        self.player = player
    }

    public func makeUIView(context: Context) -> PlayerLayerContainerView {
        let view = PlayerLayerContainerView()
        view.playerLayer.player = player
        return view
    }

    public func updateUIView(_ uiView: PlayerLayerContainerView, context: Context) {
        if uiView.playerLayer.player !== player {
            uiView.playerLayer.player = player
        }
    }
}

public final class PlayerLayerContainerView: UIView {
    public override static var layerClass: AnyClass { AVPlayerLayer.self }

    public var playerLayer: AVPlayerLayer {
        // Force-cast is safe: `layerClass` above guarantees `layer` is always
        // backed by an AVPlayerLayer for every instance of this view.
        layer as! AVPlayerLayer
    }

    public override init(frame: CGRect) {
        super.init(frame: frame)
        playerLayer.videoGravity = .resizeAspect
    }

    public required init?(coder: NSCoder) {
        super.init(coder: coder)
        playerLayer.videoGravity = .resizeAspect
    }
}
#endif
