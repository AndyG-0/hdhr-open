import Foundation
import AVFoundation
import Combine
#if os(iOS)
import AVKit
#endif

public enum PlaybackState: Equatable, Sendable {
    case idle
    case loading
    case playing
    case paused
    case buffering
    case failed(String)
}

@MainActor
public final class PlayerEngine: NSObject, ObservableObject {
    @Published public private(set) var state: PlaybackState = .idle
    @Published public private(set) var currentTime: Double = 0.0
    @Published public private(set) var duration: Double = 0.0
    @Published public private(set) var isLive: Bool = false
    @Published public private(set) var isSeekable: Bool = false
    @Published public private(set) var currentAudioTrack: HDHomeRunRecordingAudioInfo?
    @Published public private(set) var availableAudioTracks: [HDHomeRunRecordingAudioInfo] = []
    @Published public private(set) var videoSpecs: HDHomeRunRecordingVideoInfo?
    @Published public private(set) var transcodeInfo: HDHomeRunTranscodeInfo?
    @Published public private(set) var observedBitrate: Double?
    /// Whether AirPlay (or another external-playback route) is currently
    /// active - the app shell (`HDHROpeniOSApp`/`HDHROpenTVApp`) reads this
    /// to skip tearing the player down on `scenePhase == .background`, since
    /// backgrounding is the normal, expected state while AirPlaying.
    @Published public private(set) var isExternalPlaybackActive: Bool = false
    /// Whether this device/OS supports Picture in Picture at all - the
    /// player toolbar reads this to hide the PiP button entirely rather
    /// than show a control that can never work. Declared unconditionally
    /// (like `isExternalPlaybackActive`) so tvOS/macOS-test-host code never
    /// sees a missing symbol; it simply stays `false` off iOS.
    @Published public private(set) var isPictureInPictureSupported: Bool = false
    /// Whether a Picture in Picture session is currently active - read by
    /// the app shell (`HDHROpeniOSApp`) to skip tearing the player down on
    /// `scenePhase == .background`, mirroring `isExternalPlaybackActive`
    /// above, since backgrounding is the normal, expected state while PiP
    /// is showing the floating window.
    @Published public private(set) var isPictureInPictureActive: Bool = false

    public private(set) var avPlayer: AVPlayer?

    #if os(iOS)
    private var pictureInPictureController: AVPictureInPictureController?
    #endif

    private var timeObserverToken: Any?
    private var itemStatusObserver: AnyCancellable?
    private var itemAccessLogObserver: AnyCancellable?
    private var itemErrorLogObserver: AnyCancellable?
    private var itemStallObserver: AnyCancellable?
    // Lives for the lifetime of `avPlayer` (a single instance reused across
    // `loadMedia` calls via `replaceCurrentItem`), not per-item - never torn
    // down in `reset()`. `timeControlStatus` reflects whether AVPlayer is
    // actually advancing playback at rate, unlike `AVPlayerItem.isPlaybackBufferEmpty`
    // (the previous signal here), which is unreliable for near-live-edge HLS:
    // a slim live buffer window reports "empty" between segment fetches even
    // while playback proceeds smoothly, which left `state` stuck at
    // `.buffering` indefinitely - freezing both the loading spinner and the
    // controls auto-hide timer (which only runs while state == .playing).
    private var timeControlStatusObserver: AnyCancellable?
    private var externalPlaybackObserver: AnyCancellable?
    private var cancellables = Set<AnyCancellable>()

    public override init() {
        let player = AVPlayer()
        super.init()
        self.avPlayer = player
        timeControlStatusObserver = player.publisher(for: \.timeControlStatus)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] status in
                guard let self = self else { return }
                switch status {
                case .waitingToPlayAtSpecifiedRate:
                    if self.state == .playing {
                        self.state = .buffering
                    }
                case .playing:
                    if self.state == .buffering {
                        self.state = .playing
                    }
                case .paused:
                    if self.state == .buffering {
                        self.state = .paused
                    }
                @unknown default:
                    break
                }
            }

        #if canImport(UIKit)
        // Both default to true already, but set explicitly per CAST-2 - this
        // is the entry point that lets AVPlayer route to an AirPlay device at
        // all, and the second flag keeps that route alive while showing a
        // mirrored/black local screen instead of dropping back to this
        // device the moment it isn't the visible screen.
        player.allowsExternalPlayback = true
        player.usesExternalPlaybackWhileExternalScreenIsActive = true

        // Configuring the audio session is otherwise entirely absent from
        // this codebase - without `.playback`, audio (and therefore AirPlay
        // audio routing) doesn't survive the app being backgrounded or the
        // silent switch. `.moviePlayback`/`.longFormVideo` mirror Apple's own
        // guidance for a video-playback app like this one - `.longFormVideo`
        // is iOS-only (unavailable on tvOS), so tvOS gets the same category/
        // mode without a route-sharing policy override.
        #if os(iOS)
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback, policy: .longFormVideo)
        #else
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
        #endif
        try? AVAudioSession.sharedInstance().setActive(true)

        externalPlaybackObserver = player.publisher(for: \.isExternalPlaybackActive)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] isActive in
                self?.isExternalPlaybackActive = isActive
            }

        #if os(iOS)
        isPictureInPictureSupported = AVPictureInPictureController.isPictureInPictureSupported()
        #endif
        #endif
    }

    public func loadMedia(
        url: URL,
        isLive: Bool = false,
        isSeekable: Bool = true,
        initialStart: Double? = nil,
        headers: [String: String] = [:]
    ) {
        reset()
        self.isLive = isLive
        self.isSeekable = isSeekable
        self.state = .loading

        Log.player.info("Loading media: \(url.absoluteString, privacy: .public) isLive=\(isLive) isSeekable=\(isSeekable)")

        let asset: AVURLAsset
        if headers.isEmpty {
            asset = AVURLAsset(url: url)
        } else {
            // "AVURLAssetHTTPHeaderFieldsKey" has no public Swift symbol in
            // current SDKs (Apple dropped the header declaration but the
            // framework still honors the raw string key) - this is the
            // standard workaround for authenticating AVPlayer's own HLS
            // playlist/segment requests, which never go through APIClient.
            asset = AVURLAsset(url: url, options: ["AVURLAssetHTTPHeaderFieldsKey": headers])
        }
        let playerItem = AVPlayerItem(asset: asset)

        if let start = initialStart, start > 0 {
            playerItem.seek(to: CMTime(seconds: start, preferredTimescale: 600), completionHandler: nil)
        }

        setupItemObservers(for: playerItem)

        if avPlayer == nil {
            avPlayer = AVPlayer(playerItem: playerItem)
        } else {
            avPlayer?.replaceCurrentItem(with: playerItem)
        }

        setupTimeObserver()
        avPlayer?.play()
    }

    public func play() {
        avPlayer?.play()
        if state == .paused {
            state = .playing
        }
    }

    public func pause() {
        avPlayer?.pause()
        // Live HLS can flicker into `.buffering` (see `timeControlStatusObserver`
        // above) - pausing while buffering must still land on `.paused`, or
        // `state` gets stuck showing the loading spinner even though the
        // player has genuinely paused, and `togglePlayPause` below then has
        // no matching branch to recover from it.
        if state == .playing || state == .buffering {
            state = .paused
        }
    }

    public func togglePlayPause() {
        if state == .playing || state == .buffering {
            pause()
        } else if state == .paused {
            play()
        }
    }

    public func seek(to seconds: Double) {
        guard isSeekable else { return }
        let clamped = max(0, min(seconds, duration > 0 ? duration : seconds))
        // Set optimistically, before the AVPlayer seek completes, so
        // dependents that read `currentTime` right after calling `seek`
        // (e.g. caption resync) see the new position immediately.
        currentTime = clamped
        let targetTime = CMTime(seconds: clamped, preferredTimescale: 600)
        avPlayer?.seek(to: targetTime, toleranceBefore: .zero, toleranceAfter: .zero) { [weak self] _ in
            Task { @MainActor in
                self?.currentTime = clamped
            }
        }
    }

    public func skipForward(seconds: Double = 10.0) {
        seek(to: currentTime + seconds)
    }

    public func skipBackward(seconds: Double = 10.0) {
        seek(to: max(0, currentTime - seconds))
    }

    public func setAudioTracks(_ tracks: [HDHomeRunRecordingAudioInfo], selectedTrack: HDHomeRunRecordingAudioInfo? = nil) {
        self.availableAudioTracks = tracks
        if let selected = selectedTrack {
            self.currentAudioTrack = selected
        } else if self.currentAudioTrack == nil, let first = tracks.first {
            self.currentAudioTrack = first
        }
    }

    public func selectAudioTrack(_ track: HDHomeRunRecordingAudioInfo) {
        self.currentAudioTrack = track
    }

    public func setVideoSpecs(_ specs: HDHomeRunRecordingVideoInfo?) {
        self.videoSpecs = specs
    }

    public func setTranscodeInfo(_ info: HDHomeRunTranscodeInfo?) {
        self.transcodeInfo = info
    }

    public func setDuration(_ dur: Double) {
        self.duration = dur
    }

    public func setFailed(_ message: String) {
        self.state = .failed(message)
    }

    /// Callers use this to show the loading spinner immediately, before
    /// `loadMedia` is reachable - session negotiation (HTTP round trip(s) to
    /// start a watch session / HLS packaging session, plus ffmpeg's own
    /// startup) can take several seconds on its own, and without this the
    /// screen sits at `.idle` (no spinner) showing nothing but black.
    public func setLoading() {
        self.state = .loading
    }

    public func reset() {
        if let token = timeObserverToken {
            avPlayer?.removeTimeObserver(token)
            timeObserverToken = nil
        }
        itemStatusObserver?.cancel()
        itemStatusObserver = nil
        itemAccessLogObserver?.cancel()
        itemAccessLogObserver = nil
        itemErrorLogObserver?.cancel()
        itemErrorLogObserver = nil
        itemStallObserver?.cancel()
        itemStallObserver = nil

        avPlayer?.pause()
        avPlayer?.replaceCurrentItem(with: nil)

        state = .idle
        currentTime = 0.0
        duration = 0.0
        isLive = false
        isSeekable = false
        availableAudioTracks = []
        currentAudioTrack = nil
        videoSpecs = nil
        transcodeInfo = nil
        observedBitrate = nil
    }

    #if os(iOS)
    /// Called once by `PlayerLayerView.makeUIView` after it constructs the
    /// `AVPlayerLayer`-bound `AVPictureInPictureController` for the current
    /// playback session's container view - `PlayerEngine` has no
    /// `AVPlayerLayer` of its own (only `AVPlayer`), so the controller must
    /// be built where the layer lives, but engine-wide PiP state belongs
    /// alongside every other `@Published` playback flag here, not buried in
    /// a UIKit view. Each new playback session's container view calls this
    /// again, overwriting the previous controller - safe because a
    /// `PlayerLayerContainerView` (and therefore any controller bound to
    /// it) is only ever deallocated once `closePlayer()` has run, which
    /// can't happen while PiP is active (see `HDHROpeniOSApp`'s scenePhase
    /// exception).
    public func attachPictureInPictureController(_ controller: AVPictureInPictureController) {
        controller.delegate = self
        controller.canStartPictureInPictureAutomaticallyFromInline = true
        pictureInPictureController = controller
        isPictureInPictureActive = controller.isPictureInPictureActive
    }

    public func togglePictureInPicture() {
        guard let controller = pictureInPictureController else { return }
        if controller.isPictureInPictureActive {
            controller.stopPictureInPicture()
        } else {
            controller.startPictureInPicture()
        }
    }
    #endif

    private func setupTimeObserver() {
        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserverToken = avPlayer?.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            guard let self = self else { return }
            let secs = time.seconds
            if secs.isFinite && !secs.isNaN {
                Task { @MainActor in
                    self.currentTime = secs
                }
            }
        }
    }

    private func setupItemObservers(for item: AVPlayerItem) {
        itemStatusObserver = item.publisher(for: \.status)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] status in
                guard let self = self else { return }
                switch status {
                case .readyToPlay:
                    self.state = .playing
                    if let dur = self.avPlayer?.currentItem?.duration.seconds, dur.isFinite && !dur.isNaN && dur > 0 {
                        self.duration = dur
                    }
                case .failed:
                    let msg = item.error?.localizedDescription ?? "Playback failed."
                    self.state = .failed(msg)
                    Log.player.error("Player Item Failed: \(msg)")
                case .unknown:
                    break
                @unknown default:
                    break
                }
            }

        itemAccessLogObserver = NotificationCenter.default
            .publisher(for: AVPlayerItem.newAccessLogEntryNotification, object: item)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                guard let event = item.accessLog()?.events.last else { return }
                Log.player.debug("""
                    Access log: uri=\(event.uri ?? "nil", privacy: .public) \
                    indicatedBitrate=\(event.indicatedBitrate) \
                    observedBitrate=\(event.observedBitrate) \
                    bytesTransferred=\(event.numberOfBytesTransferred) \
                    serverAddressChanges=\(event.numberOfServerAddressChanges) \
                    transferDuration=\(event.transferDuration)
                    """)
                if event.observedBitrate > 0 {
                    self?.observedBitrate = event.observedBitrate
                }
            }

        itemErrorLogObserver = NotificationCenter.default
            .publisher(for: AVPlayerItem.newErrorLogEntryNotification, object: item)
            .receive(on: DispatchQueue.main)
            .sink { _ in
                guard let event = item.errorLog()?.events.last else { return }
                Log.player.error("""
                    Error log: uri=\(event.uri ?? "nil", privacy: .public) \
                    statusCode=\(event.errorStatusCode) \
                    domain=\(event.errorDomain, privacy: .public) \
                    comment=\(event.errorComment ?? "nil", privacy: .public)
                    """)
            }

        itemStallObserver = NotificationCenter.default
            .publisher(for: AVPlayerItem.playbackStalledNotification, object: item)
            .receive(on: DispatchQueue.main)
            .sink { _ in
                Log.player.warning("Playback stalled")
            }
    }
}

#if os(iOS)
extension PlayerEngine: AVPictureInPictureControllerDelegate {
    public func pictureInPictureControllerDidStartPictureInPicture(_ controller: AVPictureInPictureController) {
        isPictureInPictureActive = true
    }

    public func pictureInPictureControllerDidStopPictureInPicture(_ controller: AVPictureInPictureController) {
        isPictureInPictureActive = false
    }

    public func pictureInPictureController(
        _ controller: AVPictureInPictureController,
        failedToStartPictureInPictureWithError error: Error
    ) {
        Log.player.error("PiP failed to start: \(error.localizedDescription, privacy: .public)")
        isPictureInPictureActive = false
    }

    // `iOSPlayerView`'s visibility is driven entirely by
    // `PlayerViewModel.activeChannel`/`activeRecording` (see `RootiOSView`),
    // not a `.sheet`/`.fullScreenCover` presentation - and that state is
    // guaranteed to still be set here, since the scenePhase background
    // exception in `HDHROpeniOSApp` keeps `closePlayer()` from running while
    // PiP is active. The player UI is therefore already showing by the time
    // this fires; there is nothing to re-present.
    public func pictureInPictureController(
        _ controller: AVPictureInPictureController,
        restoreUserInterfaceForPictureInPictureStop completionHandler: @escaping (Bool) -> Void
    ) {
        completionHandler(true)
    }
}
#endif
