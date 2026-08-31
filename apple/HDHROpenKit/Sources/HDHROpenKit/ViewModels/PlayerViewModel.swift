import Foundation
import Combine

/// How the current session is being delivered - set by PlayerViewModel at
/// each stream-URL-construction call site, since PlayerEngine has no way to
/// infer this from the URL alone. Apple platforms have no direct-play path
/// today (AVFoundation can't decode raw MPEG-2/MPEG-TS), so `.direct` is
/// unused here for now, but the type keeps the UI identical in shape to
/// Android's, which does use it.
public enum PlaybackMode: Sendable {
    case direct
    case serverTranscodedHls
}

@MainActor
public final class PlayerViewModel: ObservableObject {
    public let playerEngine: PlayerEngine
    public let captionController: CaptionController
    public let watchSessionManager: WatchSessionManager

    @Published public private(set) var activeChannel: HDHomeRunChannel?
    @Published public private(set) var activeAiring: HDHomeRunGuideEntry?
    @Published public private(set) var activeRecording: HDHomeRunRecording?
    @Published public private(set) var isWatchSession: Bool = false
    @Published public private(set) var activeHLSSessionId: String?
    @Published public private(set) var playbackMode: PlaybackMode?
    @Published public private(set) var thumbnailCues: [ThumbnailCue] = []
    @Published public private(set) var thumbnailSpriteURL: URL?
    @Published public private(set) var isPromoting: Bool = false
    @Published public private(set) var isPromoted: Bool = false
    @Published public private(set) var isSwitchingAudioTrack: Bool = false
    @Published public var showAudioMenu: Bool = false
    @Published public var showSettingsOverlay: Bool = false
    @Published public var showChannelSwitcher: Bool = false

    private let apiClient: APIClient
    private var cancellables = Set<AnyCancellable>()

    public init(apiClient: APIClient, watchSessionManager: WatchSessionManager) {
        self.apiClient = apiClient
        self.watchSessionManager = watchSessionManager
        self.playerEngine = PlayerEngine()
        self.captionController = CaptionController()

        // Sync player engine time with captions
        playerEngine.$currentTime
            .sink { [weak self] time in
                self?.captionController.updatePlaybackTime(time)
            }
            .store(in: &cancellables)

        // Views only observe `playerViewModel` (via @EnvironmentObject), not
        // `playerEngine` directly - as a nested ObservableObject, playerEngine's
        // own @Published changes (state, currentTime, etc.) don't propagate to
        // those views unless forwarded here. Without this, e.g. the loading
        // spinner (driven by playerEngine.state) can go stale until some
        // unrelated @Published change on playerViewModel itself (like toggling
        // showAudioMenu) forces a redraw that happens to pick up the current
        // value.
        playerEngine.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)
    }

    public var isPlaying: Bool {
        playerEngine.state == .playing
    }

    public var mediaTitle: String {
        if let rec = activeRecording {
            return rec.title
        }
        if let ch = activeChannel {
            if let airing = activeAiring {
                return "\(ch.channelNumber) \(airing.title)"
            }
            return "\(ch.channelNumber) \(ch.name)"
        }
        return "Live TV"
    }

    /// Human-readable "how is this being played" line for the playback info
    /// panel, shared so iOS and tvOS render identical text.
    public var playbackModeLabel: String {
        switch playbackMode {
        case .direct:
            return "Direct (client-side)"
        case .serverTranscodedHls:
            if let presetLabel = playerEngine.transcodeInfo?.presetLabel {
                let hw = playerEngine.transcodeInfo?.hardware == true ? " (HW)" : ""
                return "Server transcoded via \(presetLabel)\(hw)"
            }
            return "Server transcoded (HLS)"
        case nil:
            return "Unknown"
        }
    }

    public var mediaSubtitle: String? {
        if let rec = activeRecording {
            if let ep = rec.episodeTitle, let des = rec.episodeDesignation {
                return "\(des) • \(ep)"
            }
            return rec.episodeTitle ?? rec.episodeDesignation ?? rec.channelName
        }
        if let airing = activeAiring {
            if let ep = airing.episodeTitle, let num = airing.episodeNumber {
                return "\(num) • \(ep)"
            }
            return airing.episodeTitle ?? airing.synopsis
        }
        return activeChannel?.name
    }

    public func playChannel(channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry? = nil) async {
        closePlayer()
        self.activeChannel = channel
        self.activeAiring = airing ?? channel.now
        playerEngine.setLoading()

        let baseURL = await apiClient.baseURL

        // 1. Try starting a watch session for live pause/rewind, packaged as HLS
        do {
            if let watchRec = try await watchSessionManager.startWatch(channelNumber: channel.channelNumber),
               let playUrl = watchRec.playUrl {
                let hlsSession = try await apiClient.createRecordingHLSSession(
                    url: playUrl,
                    recordingId: watchRec.recordingId
                )
                if let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: hlsSession.sessionId) {
                    Log.player.info("Watch session HLS: sessionId=\(hlsSession.sessionId, privacy: .public) url=\(playlistURL.absoluteString, privacy: .public)")
                    self.activeRecording = watchRec
                    self.isWatchSession = true
                    self.activeHLSSessionId = hlsSession.sessionId
                    self.playbackMode = .serverTranscodedHls
                    playerEngine.loadMedia(url: playlistURL, isLive: true, isSeekable: true, headers: await hlsAuthHeaders())
                    loadRecordingMetadata(recording: watchRec)
                    return
                }
            }
        } catch {
            Log.player.warning("Watch session auto-start failed, falling back to direct HLS stream: \(error.localizedDescription)")
        }

        // 2. Direct HLS streaming fallback (busy tuner / no watch session)
        do {
            let hlsSession = try await apiClient.createChannelHLSSession(channelNumber: channel.channelNumber)
            guard let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: hlsSession.sessionId) else {
                playerEngine.setFailed("Could not build stream URL.")
                return
            }
            Log.player.info("Direct channel HLS: sessionId=\(hlsSession.sessionId, privacy: .public) url=\(playlistURL.absoluteString, privacy: .public)")
            self.isWatchSession = false
            self.activeRecording = nil
            self.activeHLSSessionId = hlsSession.sessionId
            self.playbackMode = .serverTranscodedHls
            playerEngine.loadMedia(url: playlistURL, isLive: true, isSeekable: false, headers: await hlsAuthHeaders())
        } catch {
            Log.player.error("Direct HLS channel stream failed: \(error.localizedDescription)")
            playerEngine.setFailed(error.localizedDescription)
        }
    }

    public func playRecording(_ recording: HDHomeRunRecording) async {
        closePlayer()
        self.activeRecording = recording
        self.activeChannel = nil
        self.activeAiring = nil
        self.isWatchSession = false
        playerEngine.setLoading()

        let baseURL = await apiClient.baseURL
        guard let playUrl = recording.playUrl, !playUrl.isEmpty else {
            playerEngine.setFailed("No playable URL for this recording.")
            return
        }

        do {
            let hlsSession = try await apiClient.createRecordingHLSSession(
                url: playUrl,
                recordingId: recording.recordingId
            )
            guard let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: hlsSession.sessionId) else {
                playerEngine.setFailed("Could not build stream URL.")
                return
            }
            Log.player.info("Recording HLS: sessionId=\(hlsSession.sessionId, privacy: .public) url=\(playlistURL.absoluteString, privacy: .public)")
            self.activeHLSSessionId = hlsSession.sessionId
            self.playbackMode = .serverTranscodedHls
            playerEngine.loadMedia(url: playlistURL, isLive: recording.isInProgress, isSeekable: true, headers: await hlsAuthHeaders())
            loadRecordingMetadata(recording: recording)
        } catch {
            Log.player.error("Recording HLS stream failed: \(error.localizedDescription)")
            playerEngine.setFailed(error.localizedDescription)
        }
    }

    public func promoteToRecording() async {
        guard isWatchSession, !isPromoting else { return }
        isPromoting = true
        defer { isPromoting = false }

        do {
            let promoted = try await watchSessionManager.promoteWatch()
            self.activeRecording = promoted
            self.isPromoted = true
            Log.player.info("Promoted live watch to DVR recording: \(promoted.title)")
        } catch {
            Log.player.error("Failed to promote watch session: \(error.localizedDescription)")
        }
    }

    /// Audio track selection is baked into the HLS packaging itself
    /// (backend maps a specific source audio stream via ffmpeg's `-map`
    /// when building the session) rather than exposed as switchable
    /// `AVMediaSelectionOption`s on the produced stream, so "switching"
    /// requires starting a new HLS session with the new audio index and
    /// resuming playback at the current position.
    public func selectAudioTrack(_ track: HDHomeRunRecordingAudioInfo) async {
        guard !isSwitchingAudioTrack, track.index != playerEngine.currentAudioTrack?.index else { return }
        guard let recording = activeRecording, let playUrl = recording.playUrl, !playUrl.isEmpty else { return }

        isSwitchingAudioTrack = true
        defer { isSwitchingAudioTrack = false }

        let resumeTime = playerEngine.currentTime
        let isLive = playerEngine.isLive
        let isSeekable = playerEngine.isSeekable
        let previousSessionId = activeHLSSessionId
        let previousAudioTracks = playerEngine.availableAudioTracks
        let previousVideoSpecs = playerEngine.videoSpecs
        let previousTranscodeInfo = playerEngine.transcodeInfo
        let baseURL = await apiClient.baseURL

        do {
            let hlsSession = try await apiClient.createRecordingHLSSession(
                url: playUrl,
                recordingId: recording.recordingId,
                start: resumeTime,
                audioIndex: track.index
            )
            guard let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: hlsSession.sessionId) else {
                Log.player.error("Audio track switch failed: could not build stream URL.")
                return
            }
            Log.player.info("Audio track switch: sessionId=\(hlsSession.sessionId, privacy: .public) audioIndex=\(track.index)")
            activeHLSSessionId = hlsSession.sessionId
            // loadMedia() calls reset() internally, which wipes the audio
            // track list/video specs - restore them since they describe the
            // underlying recording and don't change when only the mapped
            // audio stream does.
            playerEngine.loadMedia(url: playlistURL, isLive: isLive, isSeekable: isSeekable, headers: await hlsAuthHeaders())
            playerEngine.setAudioTracks(previousAudioTracks)
            playerEngine.setVideoSpecs(previousVideoSpecs)
            playerEngine.setTranscodeInfo(previousTranscodeInfo)
            playerEngine.selectAudioTrack(track)

            if let previousSessionId {
                let apiClient = self.apiClient
                runWithBackgroundGrace(name: "StopHLSSession") {
                    try? await apiClient.stopHLSSession(sessionId: previousSessionId)
                }
            }
        } catch {
            Log.player.error("Audio track switch failed: \(error.localizedDescription)")
        }
    }

    private func hlsAuthHeaders() async -> [String: String] {
        guard let token = await apiClient.currentBearerToken() else { return [:] }
        return ["Authorization": "Bearer \(token)"]
    }

    private func loadRecordingMetadata(recording: HDHomeRunRecording) {
        guard let recId = recording.recordingId, let playUrl = recording.playUrl else { return }

        Task {
            let baseURL = await apiClient.baseURL

            // Fetch Detail (audio tracks, video specs)
            if let detail = try? await apiClient.getRecordingDetail(url: playUrl, recordingId: recId, recordEnd: recording.recordEnd) {
                playerEngine.setAudioTracks(detail.audio)
                playerEngine.setVideoSpecs(detail.video)
                playerEngine.setTranscodeInfo(detail.transcode)
                if let dur = detail.durationSeconds, dur > 0 {
                    playerEngine.setDuration(dur)
                }
            }

            // Fetch Thumbnails VTT
            if let vttURL = StreamURLBuilder.thumbnailVttURL(baseURL: baseURL, recordingId: recId, playUrl: playUrl, recordEnd: recording.recordEnd) {
                self.thumbnailSpriteURL = StreamURLBuilder.thumbnailSpriteURL(baseURL: baseURL, recordingId: recId, playUrl: playUrl, recordEnd: recording.recordEnd)
                if let (data, _) = try? await URLSession.shared.data(from: vttURL),
                   let vttString = String(data: data, encoding: .utf8) {
                    self.thumbnailCues = VTTParser.parseThumbnailVtt(from: vttString)
                }
            }

            // Fetch Captions VTT
            if let capURL = StreamURLBuilder.captionsURL(baseURL: baseURL, recordingId: recId, playUrl: playUrl, recordEnd: recording.recordEnd) {
                if let (data, _) = try? await URLSession.shared.data(from: capURL),
                   let vttString = String(data: data, encoding: .utf8) {
                    let cues = VTTParser.parseCaptions(from: vttString)
                    captionController.setCues(cues)
                }
            }
        }
    }

    public func closePlayer() {
        playerEngine.reset()
        watchSessionManager.stopWatch()
        if let sessionId = activeHLSSessionId {
            let apiClient = self.apiClient
            runWithBackgroundGrace(name: "StopHLSSession") {
                try? await apiClient.stopHLSSession(sessionId: sessionId)
            }
        }
        activeChannel = nil
        activeAiring = nil
        activeRecording = nil
        isWatchSession = false
        activeHLSSessionId = nil
        playbackMode = nil
        isPromoted = false
        thumbnailCues = []
        thumbnailSpriteURL = nil
    }
}
