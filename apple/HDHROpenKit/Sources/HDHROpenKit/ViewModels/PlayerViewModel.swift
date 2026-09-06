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
    @Published public internal(set) var activeRecording: HDHomeRunRecording?
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
    @Published public var showRecordMenu: Bool = false
    @Published public var showSyncPlaySheet: Bool = false

    public let syncPlayClient: SyncPlayClient

    private let apiClient: APIClient
    private var cancellables = Set<AnyCancellable>()

    // Live caption polling/alignment state (CC-7). Declared without
    // `private` (rather than Android's reflection-based test access) so
    // `@testable import` test code can seed and inspect it directly.
    static let captionPollIntervalNanos: UInt64 = 1_500_000_000 // 1.5s, mirrors Android's CAPTION_POLL_INTERVAL_MS
    static let liveCueStretchSeconds: Double = 4.0 // mirrors Android's LIVE_CUE_STRETCH_SECONDS
    // Caps how far behind "now" a stretched cue's slot can be pushed by a
    // burst of backlog (see alignLiveCues's cursor-reset comment for why
    // this exists - mirrors web's caption-controller.ts LIVE_CUE_MAX_
    // CATCHUP_SECONDS from the CC-13 freeze fix). Past this cap, further
    // backlog cues are left unstretched (naturally expired, dropped from
    // display) instead of extending the queue arbitrarily far forward.
    static let liveCueMaxCatchupSeconds: Double = 20.0
    var lastRawCues: [CaptionCue] = []
    var stretchedCueDisplay: [String: (start: Double, end: Double)] = [:]
    var nextStretchSlotAbsolute: Double = 0.0
    private var captionPollTask: Task<Void, Never>?

    public init(apiClient: APIClient, watchSessionManager: WatchSessionManager) {
        self.apiClient = apiClient
        self.watchSessionManager = watchSessionManager
        self.playerEngine = PlayerEngine()
        self.captionController = CaptionController()
        self.syncPlayClient = SyncPlayClient()

        // Sync player engine time with captions
        playerEngine.$currentTime
            .sink { [weak self] time in
                self?.captionController.updatePlaybackTime(time)
            }
            .store(in: &cancellables)

        // Views only observe `playerViewModel` (via @EnvironmentObject), not
        // `playerEngine` directly - as a nested ObservableObject, playerEngine's
        // own @Published changes (state, currentTime, etc.) don't propagate to
        // those views unless forwarded here.
        playerEngine.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        // Forward syncPlayClient changes
        syncPlayClient.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        syncPlayClient.getCurrentPosition = { [weak self] in
            self?.playerEngine.currentTime ?? 0.0
        }

        syncPlayClient.isPlayerReady = { [weak self] in
            guard let self = self else { return false }
            return self.playerEngine.state == .playing || self.playerEngine.state == .paused
        }

        syncPlayClient.onRemotePlay = { [weak self] pos, rate in
            guard let self = self else { return }
            let diff = abs(self.playerEngine.currentTime - pos)
            if diff > 2.0 {
                self.playerEngine.seek(to: pos)
            }
            self.playerEngine.play()
        }

        syncPlayClient.onRemotePause = { [weak self] pos in
            guard let self = self else { return }
            self.playerEngine.pause()
            let diff = abs(self.playerEngine.currentTime - pos)
            if diff > 0.5 {
                self.playerEngine.seek(to: pos)
            }
        }

        syncPlayClient.onRemoteSeek = { [weak self] pos in
            guard let self = self else { return }
            self.playerEngine.seek(to: pos)
        }

        syncPlayClient.onRemoteContentChange = { [weak self] content in
            Task { @MainActor [weak self] in
                self?.handleRemoteContentChange(content)
            }
        }
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

        if syncPlayClient.isConnected && syncPlayClient.isHost {
            syncPlayClient.changeContent(
                SyncPlayContent(
                    type: "channel",
                    channelNumber: channel.channelNumber,
                    title: airing?.title ?? channel.name
                )
            )
        }

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
            let rec = try await apiClient.createChannelHLSSession(channelNumber: channel.channelNumber)
            guard let sessionId = rec.sessionId,
                  let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: sessionId) else {
                playerEngine.setFailed("Could not build stream URL.")
                return
            }
            Log.player.info("Direct channel HLS: sessionId=\(sessionId, privacy: .public) url=\(playlistURL.absoluteString, privacy: .public)")
            self.isWatchSession = false
            self.activeRecording = rec.recordingId != nil ? rec : nil
            self.activeHLSSessionId = sessionId
            self.playbackMode = .serverTranscodedHls
            playerEngine.loadMedia(url: playlistURL, isLive: true, isSeekable: false, headers: await hlsAuthHeaders())
            if rec.recordingId != nil {
                loadRecordingMetadata(recording: rec)
            }
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

        if syncPlayClient.isConnected && syncPlayClient.isHost {
            syncPlayClient.changeContent(
                SyncPlayContent(
                    type: "recording",
                    recordingId: recording.recordingId,
                    channelNumber: recording.channelNumber,
                    title: recording.title,
                    durationSeconds: recording.durationSeconds
                )
            )
        }

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
            let sessionId: String
            if let recording = activeRecording, let playUrl = recording.playUrl, !playUrl.isEmpty {
                let hlsSession = try await apiClient.createRecordingHLSSession(
                    url: playUrl,
                    recordingId: recording.recordingId,
                    start: resumeTime,
                    audioIndex: track.index
                )
                sessionId = hlsSession.sessionId
            } else if let channel = activeChannel {
                let rec = try await apiClient.createChannelHLSSession(channelNumber: channel.channelNumber, audioIndex: track.index)
                guard let recSessionId = rec.sessionId else {
                    Log.player.error("Audio track switch failed: no session id for channel HLS.")
                    return
                }
                sessionId = recSessionId
            } else {
                return
            }

            guard let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: sessionId) else {
                Log.player.error("Audio track switch failed: could not build stream URL.")
                return
            }
            Log.player.info("Audio track switch: sessionId=\(sessionId, privacy: .public) audioIndex=\(track.index)")
            activeHLSSessionId = sessionId
            // loadMedia() calls reset() internally, which wipes the audio
            // track list/video specs - restore them with the selected track atomically.
            playerEngine.loadMedia(url: playlistURL, isLive: isLive, isSeekable: isSeekable, headers: await hlsAuthHeaders())
            playerEngine.setAudioTracks(previousAudioTracks, selectedTrack: track)
            playerEngine.setVideoSpecs(previousVideoSpecs)
            playerEngine.setTranscodeInfo(previousTranscodeInfo)

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

            // Fetch Captions VTT, then start live polling if this recording
            // is still in progress.
            await fetchCaptionsOnce(recording: recording)
            startCaptionPolling(recording: recording)
        }
    }

    /// Fetches and parses the caption VTT once, then aligns/stretches it
    /// against the player's current clock before publishing it to
    /// `captionController`. Best-effort: captions may not be extracted yet
    /// for an in-progress recording, so any failure here is swallowed - a
    /// poller (if running) retries on the next tick.
    private func fetchCaptionsOnce(recording: HDHomeRunRecording) async {
        guard let recId = recording.recordingId, let playUrl = recording.playUrl else { return }
        let baseURL = await apiClient.baseURL
        guard let capURL = StreamURLBuilder.captionsURL(baseURL: baseURL, recordingId: recId, playUrl: playUrl, recordEnd: recording.recordEnd) else { return }
        guard let (data, _) = try? await URLSession.shared.data(from: capURL),
              let vttString = String(data: data, encoding: .utf8) else { return }
        let cues = VTTParser.parseCaptions(from: vttString)
        lastRawCues = cues
        captionController.setCues(alignLiveCues(recording: recording, cues: cues))
    }

    /// Re-fetches captions every `captionPollIntervalNanos` while `recording`
    /// is in progress, so live captions keep appearing as CC extraction
    /// catches up. No-ops for an already-finished recording. Always does one
    /// more fetch right after the recording transitions out of "in
    /// progress" to pick up the final complete VTT before stopping.
    private func startCaptionPolling(recording: HDHomeRunRecording) {
        guard recording.isInProgress else { return }
        captionPollTask?.cancel()
        captionPollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: Self.captionPollIntervalNanos)
                guard let self, let current = self.activeRecording else { break }
                let wasInProgress = current.isInProgress
                await self.fetchCaptionsOnce(recording: current)
                if !wasInProgress { break }
            }
        }
    }

    /// Remaps raw cue timestamps (anchored to the capture's absolute
    /// wall-clock start) onto the player's own rolling-live-window clock,
    /// and "stretches" any cue whose natural shifted end has already passed
    /// the current player time into a synthetic display window - CC
    /// extraction lag routinely runs well past a cue's own few-second
    /// window, so without this such cues would never satisfy
    /// `CaptionCue.contains` and would silently never display. Recomputed
    /// fresh on every call (not cached) since `baseOffsetSeconds` shifts as
    /// the live HLS window grows; only the per-cue stretch *decision* is
    /// memoized (keyed by cue id, which is stable across re-fetches) so a
    /// re-poll or re-seek reuses the same synthetic window instead of
    /// flickering it. VOD/finished recordings pass through untouched.
    private func alignLiveCues(recording: HDHomeRunRecording, cues: [CaptionCue]) -> [CaptionCue] {
        guard recording.isInProgress, let start = recording.start else { return cues }

        let elapsedCaptureSeconds = Date().timeIntervalSince1970 - start
        let playerTime = playerEngine.currentTime
        let baseOffsetSeconds = elapsedCaptureSeconds - playerTime

        // Re-anchor to "now" on every call instead of trusting wherever a
        // previous, separate call left the cursor. Without this, the cursor
        // advances by liveCueStretchSeconds per newly-stretched cue - slower
        // than real cue cadence (~2.85s avg observed) - so it drifts further
        // ahead of real time on every poll and never catches back up, pinning
        // near the cap below and queuing every cue after that behind an
        // unreachable backlog: a permanent freeze, not a bounded lag. Same
        // bug and fix as web's caption-controller.ts (CC-13).
        nextStretchSlotAbsolute = elapsedCaptureSeconds

        return cues.compactMap { cue in
            let window: (start: Double, end: Double)
            if let stretched = stretchedCueDisplay[cue.id] {
                window = stretched
            } else {
                let naturalEnd = cue.end - baseOffsetSeconds
                if naturalEnd > playerTime {
                    window = (cue.start, cue.end)
                } else {
                    let slotStart = max(cue.start, max(nextStretchSlotAbsolute, elapsedCaptureSeconds))
                    if slotStart - elapsedCaptureSeconds > Self.liveCueMaxCatchupSeconds {
                        window = (cue.start, cue.end)
                    } else {
                        let slotEnd = slotStart + Self.liveCueStretchSeconds
                        stretchedCueDisplay[cue.id] = (slotStart, slotEnd)
                        nextStretchSlotAbsolute = slotEnd
                        window = (slotStart, slotEnd)
                    }
                }
            }
            let displayEnd = window.end - baseOffsetSeconds
            guard displayEnd > 0 else { return nil }
            let displayStart = max(0, window.start - baseOffsetSeconds)
            return CaptionCue(start: displayStart, end: displayEnd, text: cue.text)
        }
    }

    public func play() {
        playerEngine.play()
        if syncPlayClient.isConnected {
            syncPlayClient.sendPlay(position: playerEngine.currentTime)
        }
    }

    public func pause() {
        playerEngine.pause()
        if syncPlayClient.isConnected {
            syncPlayClient.sendPause(position: playerEngine.currentTime)
        }
    }

    public func togglePlayPause() {
        if playerEngine.state == .playing {
            pause()
        } else {
            play()
        }
    }

    public func seek(to seconds: Double) {
        playerEngine.seek(to: seconds)
        resyncCaptionsAfterSeek()
        if syncPlayClient.isConnected {
            syncPlayClient.sendSeek(position: seconds)
        }
    }

    public func skipForward(seconds: Double = 10.0) {
        let target = playerEngine.currentTime + seconds
        seek(to: target)
    }

    public func skipBackward(seconds: Double = 10.0) {
        let target = max(0, playerEngine.currentTime - seconds)
        seek(to: target)
    }

    public func createSyncPlayRoom(userName: String) async throws -> SyncPlayRoom {
        let content = currentSyncPlayContent()
        let resp = try await apiClient.createSyncPlayRoom(userName: userName, initialContent: content)
        if let wsUrl = await apiClient.syncPlayWsUrl(roomCode: resp.room.roomCode, userName: userName) {
            syncPlayClient.connect(url: wsUrl)
        }
        return resp.room
    }

    public func joinSyncPlayRoom(roomCode: String, userName: String) async throws {
        guard let wsUrl = await apiClient.syncPlayWsUrl(roomCode: roomCode, userName: userName) else {
            throw APIError.invalidURL
        }
        syncPlayClient.connect(url: wsUrl)
    }

    public func leaveSyncPlayRoom() {
        syncPlayClient.disconnect()
    }

    public func transferSyncPlayHost(targetSessionId: String) {
        syncPlayClient.transferHost(targetSessionId: targetSessionId)
    }

    public func currentSyncPlayContent() -> SyncPlayContent? {
        if let rec = activeRecording {
            return SyncPlayContent(
                type: "recording",
                recordingId: rec.recordingId,
                channelNumber: rec.channelNumber,
                title: rec.title,
                durationSeconds: playerEngine.duration > 0 ? playerEngine.duration : rec.durationSeconds
            )
        }
        if let ch = activeChannel {
            return SyncPlayContent(
                type: "channel",
                channelNumber: ch.channelNumber,
                title: activeAiring?.title ?? ch.name
            )
        }
        return nil
    }

    /// Re-runs cue alignment against `lastRawCues` immediately after a
    /// seek/skip, instead of waiting for the next poll tick (which could be
    /// up to `captionPollIntervalNanos` away). No network call - the
    /// underlying VTT content hasn't changed, only the player's position.
    /// No-op for a finished/VOD recording, whose cue timestamps are static.
    /// Deliberately does not touch `stretchedCueDisplay`:
    /// `alignLiveCues` recomputes display coordinates fresh on every call
    /// from stretch windows stored in absolute time, so there's no stale
    /// state to clear. Clearing it here would be actively harmful - since
    /// each poll re-fetches and re-parses the *entire* caption history
    /// (full replace, not incremental), clearing the map would make every
    /// already-stretched cue in `lastRawCues` look "newly arrived"
    /// simultaneously, replaying the whole caption history in back-to-back
    /// stretch slots right after a seek.
    private func resyncCaptionsAfterSeek() {
        guard let recording = activeRecording, recording.isInProgress else { return }
        captionController.setCues(alignLiveCues(recording: recording, cues: lastRawCues))
    }

    private func resetCueStretch() {
        stretchedCueDisplay.removeAll()
        nextStretchSlotAbsolute = 0.0
        lastRawCues = []
    }

    public func closePlayer() {
        playerEngine.reset()
        captionPollTask?.cancel()
        captionPollTask = nil
        resetCueStretch()
        captionController.reset()
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

    private func handleRemoteContentChange(_ content: SyncPlayContent) {
        Task { @MainActor [weak self] in
            guard let self = self else { return }
            if content.type == "recording", let recId = content.recordingId, !recId.isEmpty {
                if activeRecording?.recordingId != recId {
                    let dummyRec = HDHomeRunRecording(
                        recordingId: recId,
                        title: content.title ?? "Recording",
                        channelNumber: content.channelNumber,
                        playUrl: "/api/recordings/stream/\(recId)"
                    )
                    Task {
                        await playRecording(dummyRec)
                    }
                }
            } else if content.type == "channel", let chNum = content.channelNumber, !chNum.isEmpty {
                if activeChannel?.channelNumber != chNum {
                    let dummyCh = HDHomeRunChannel(
                        channelNumber: chNum,
                        name: content.title ?? chNum
                    )
                    Task {
                        await playChannel(channel: dummyCh)
                    }
                }
            }
        }
    }
}
