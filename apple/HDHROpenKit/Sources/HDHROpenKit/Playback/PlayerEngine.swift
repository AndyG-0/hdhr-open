import Foundation
import AVFoundation
import Combine

public enum PlaybackState: Equatable, Sendable {
    case idle
    case loading
    case playing
    case paused
    case buffering
    case failed(String)
}

@MainActor
public final class PlayerEngine: ObservableObject {
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

    public private(set) var avPlayer: AVPlayer?

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
    private var cancellables = Set<AnyCancellable>()

    public init() {
        let player = AVPlayer()
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
        let targetTime = CMTime(seconds: max(0, min(seconds, duration > 0 ? duration : seconds)), preferredTimescale: 600)
        avPlayer?.seek(to: targetTime, toleranceBefore: .zero, toleranceAfter: .zero) { [weak self] _ in
            Task { @MainActor in
                self?.currentTime = seconds
            }
        }
    }

    public func skipForward(seconds: Double = 10.0) {
        seek(to: currentTime + seconds)
    }

    public func skipBackward(seconds: Double = 10.0) {
        seek(to: max(0, currentTime - seconds))
    }

    public func setAudioTracks(_ tracks: [HDHomeRunRecordingAudioInfo]) {
        self.availableAudioTracks = tracks
        if self.currentAudioTrack == nil, let first = tracks.first {
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
